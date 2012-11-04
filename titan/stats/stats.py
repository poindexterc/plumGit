#!/usr/bin/env python
# Copyright 2012 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Customizable numeric counters for recording time-tracked app statistics.

Usage:
  # Increment a counter for some particular stat, like a page view:
  page_view_counter = stats.Counter('page/view')
  page_view_counter.Increment()

  # Or measure the average latency of any arbitrary code block:
  latency_counter = stats.AverageTimingCounter('widget/render/latency')
  latency_counter.Start()
  # ... code block ...
  latency_counter.Stop()

  # Store the counters in the local request environment.
  stats.StoreRequestLocalCounters([latency_counter, page_view_counter])

  # Save the counter (this should happen at the absolute end of a request).
  stats.SaveRequestLocalCounters()

  # In a cron job run every minute:
  all_counters = [stats.Counter('page/view')]
  aggregator = stats.Aggregator(all_counters)
  aggregator.ProcessWindowsWithBackoff(total_runtime_minutes=1)

Internal design and terminology:
  - "Window" or "aggregation window" used below is a unix timestamp rounded to
    some number of seconds. Each window can be thought of as a bucket of time
    used to hold counter data. Each window is also the unit-of-aggregation for
    data, meaning that if the window size is 10 seconds, there will potentially
    be 8640 data points stored permanently per day, per counter (since there
    are 86400 seconds in a day).

  - The counters work in two steps:
    1. Application code creates, increments, and saves counters during a
       request. When saving counters, a task is added to a pull task queue.
    2. A cron job runs the Aggregator to collect, aggregate, and store counter
       data. Even though cron jobs can only be started at minute-level
       intervals, the cron job runs continuously for the entire minute,
       collecting data from aggregation windows which have already passed
       and pausing dynamically if all old windows have been collected.
"""

import copy
import datetime
import json
import logging
import os
import time
from google.appengine.api import taskqueue
from titan import files

# The bucket size for an aggregation window, in number of seconds.
DEFAULT_WINDOW_SIZE = 10

TASKQUEUE_NAME = 'titan-stats'
TASKQUEUE_LEASE_SECONDS = 480  # 8 minutes.
TASKQUEUE_LEASE_MAX_TASKS = 1000

# The number of seconds before an added task is allowed to be leased.
# This prevents the aggregator from prematurely consuming the tasks when
# the window hasn't yet passed.
TASKQUEUE_LEASE_BUFFER_SECONDS = 3 * DEFAULT_WINDOW_SIZE

BASE_DIR = '/_titan/stats/counters'
DATA_FILENAME = 'data-%ss.json' % DEFAULT_WINDOW_SIZE

class AbstractBaseCounter(object):
  """Base class for all counters."""

  def __init__(self, name):
    self.name = name
    if ':' in self.name:
      raise ValueError('":" is not allowed in counter name: %s'
                       % name)
    if name.startswith('/') or name.endswith('/'):
      raise ValueError('"/" is not allowed to begin or end counter name: %s'
                       % name)

  def __repr__(self):
    return '<%s %s>' % (self.__class__.__name__, self.name)

  def Aggregate(self, value):
    """Abstract method, must aggregate data together before Finalize."""
    raise NotImplementedError('Subclasses should implement abstract method.')

  def Finalize(self):
    """Abstract method; must be idempotent and return finalized counter data."""
    raise NotImplementedError('Subclasses should implement abstract method.')

class Counter(AbstractBaseCounter):
  """The simplest of counters; providing offsets to a single value."""

  def __init__(self, *args, **kwargs):
    super(Counter, self).__init__(*args, **kwargs)
    self._value = 0

  def __repr__(self):
    return '<Counter %s %s>' % (self.name, self._value)

  def Increment(self):
    """Increment the counter by one."""
    self._value += 1

  def Offset(self, value):
    """Offset the counter by some value."""
    self._value += value

  def Aggregate(self, value):
    self.Offset(value)

  def Finalize(self):
    return self._value

class AverageCounter(Counter):
  """A cumulative moving average counter.

  Each data point will represent the average during the aggregation window;
  averages are not affected by values from previous aggregation windows.
  """

  def __init__(self, *args, **kwargs):
    super(AverageCounter, self).__init__(*args, **kwargs)
    self._weight = 0

  def Increment(self):
    self.Aggregate((1, 1))  # (value, weight)

  def Offset(self, value):
    self.Aggregate((value, 1))  # (value, weight)

  def Aggregate(self, value):
    # Cumulative moving average:
    # (n*weight(n) + m*weight(m)) / (weight(n) + weight(m))
    value, weight = value
    # Numerator:
    self._value *= self._weight
    self._value += value * weight
    # Denominator:
    self._weight += weight
    self._value /= float(self._weight)

  def Finalize(self):
    return (self._value, self._weight)

class AverageTimingCounter(AverageCounter):
  """An AverageCounter with convenience methods for timing code blocks.

  Records data in millisecond integers.

  Usage:
    timing_counter = AverageTimingCounter('page/render/latency')
    timing_counter.Start()
    ...page render logic...
    timing_counter.Stop()
  """

  def __init__(self, *args, **kwargs):
    super(AverageTimingCounter, self).__init__(*args, **kwargs)
    self._start = None

  def Start(self):
    assert self._start is None, 'Counter started again without stopping.'
    self._start = time.time()

  def Stop(self):
    self.Offset(int((time.time() - self._start) * 1000))
    self._start = None

  def Finalize(self):
    assert self._start is None, 'Counter finalized without stopping.'
    value, weight = super(AverageTimingCounter, self).Finalize()
    return (int(value), weight)

def StoreRequestLocalCounters(counters):
  """Store given counters in a request/thread-local environment var."""
  counters = counters if hasattr(counters, '__iter__') else [counters]
  if not 'counters' in os.environ:
    # os.environ is replaced by the runtime environment with a request-local
    # object, allowing non-string types to be stored globally in the environment
    # and automatically cleaned up at the end of each request.
    os.environ['counters'] = []
  os.environ['counters'] += counters

def GetRequestLocalCounters():
  """Get all environment counters."""
  return os.environ.get('counters', [])

def SaveRequestLocalCounters():
  """Save all environment counters for future aggregation."""
  return SaveCounters(GetRequestLocalCounters())

def SaveCounters(counters, timestamp=None):
  """Save counter data to a aggregation window.

  Args:
    counters: An iterable of counters.
    timestamp: A unix timestamp. Defaults to the current time if not given.
    _countdown: An internal argument, specifying the task countdown.
  Raises:
    ValueError: if passed an empty list of counters.
  Result:
    A dictionary mapping counter keys to finalized data.
  """
  counters = counters if hasattr(counters, '__iter__') else [counters]
  if not counters:
    raise ValueError('Counters are required. Got: %r' % counters)
  window = _GetWindow(time.time() if timestamp is None else timestamp)
  counter_data = {
      'window': window,
      'counters': {},
  }
  for counter in counters:
    counter_data['counters'][counter.name] = counter.Finalize()
  counter_data = json.dumps(counter_data)
  # Important: unlock this window's tasks for lease at the same time,
  # after the window itself has passed.
  eta = datetime.datetime.utcfromtimestamp(
      window + TASKQUEUE_LEASE_BUFFER_SECONDS)
  try:
    task = taskqueue.Task(
        method='PULL',
        payload=counter_data,
        tag=str(window),
        eta=eta)
    task.add(queue_name=TASKQUEUE_NAME)
    return counter_data
  except taskqueue.Error:
    # Task queue errors from SaveCounters should not kill a request.
    logging.exception('Unable to add stats task to queue.')

class Aggregator(object):
  """A service class, used in a cron job to consume and save counters."""

  def __init__(self, counters):
    self._original_counters = copy.deepcopy(counters)
    self._ResetCounters()

  def _ResetCounters(self):
    self.counters = copy.deepcopy(self._original_counters)
    self._names_to_counters = {}
    for counter in self.counters:
      self._names_to_counters[counter.name] = counter

  def ProcessNextWindow(self):
    """Lease tasks and permanently save a window's-worth of counter data tasks.

    Returns:
      A dictionary containing "window" and "counters", where window is an
      integer and counters is a dictionary mapping counter names to aggregate
      data. Returns an empty dictionary if no tasks were available to consume.
    """
    self._ResetCounters()
    queue = taskqueue.Queue(TASKQUEUE_NAME)

    # Grab the first task to get its window.
    tasks = queue.lease_tasks(lease_seconds=TASKQUEUE_LEASE_SECONDS,
                              max_tasks=1)
    if not tasks:
      return {}
    # Lease tasks by window tag.
    tasks_in_window = queue.lease_tasks_by_tag(
        lease_seconds=TASKQUEUE_LEASE_SECONDS,
        max_tasks=TASKQUEUE_LEASE_MAX_TASKS,
        tag=tasks[0].tag)
    tasks.extend(tasks_in_window)

    current_window = json.loads(tasks[0].payload)['window']
    data_to_aggregate = []
    for task in tasks:
      counter_data = json.loads(task.payload)
      data_to_aggregate.append(counter_data)

    # Aggregate the counter data into each counter object.
    available_counter_names = set()
    for counter_data in data_to_aggregate:
      for counter_name, counter_value in counter_data['counters'].iteritems():
        self._names_to_counters[counter_name].Aggregate(counter_value)
        available_counter_names.add(counter_name)

    # Store each counter's finalized data into aggregate_data.
    aggregate_data = {
        'counters': {},
        'window': current_window,
    }
    if not available_counter_names:
      return {}
    for counter in self.counters:
      if counter.name not in available_counter_names:
        # Don't store anything for counters with no data in this window.
        continue
      aggregate_data['counters'][counter.name] = counter.Finalize()

    # Save data, then delete tasks whose data we have consumed.
    self._SaveAggregateData(aggregate_data)
    queue.delete_tasks(tasks)

    return aggregate_data

  def ProcessWindowsWithBackoff(self, total_runtime_minutes, development=False):
    """Long-running function to process multiple windows.

    Args:
      total_runtime_minutes: How long to process data for.
    Returns:
      A list of results from ProcessNextWindow().
    """
    results = []
    backoff = 1
    end_time = time.time() + (total_runtime_minutes * 60)
    if development:
        # if development, switch to 5 seconds instead of using minutes
        end_time = time.time() + 5

    while True:
      result = self.ProcessNextWindow()
      results.append(result)
      if result:
        backoff = 1
      else:
        if time.time() + backoff > end_time:
          # If we're about to sleep past the end times, just quit now.
          break
        time.sleep(backoff)
        backoff *= 2
        if backoff > DEFAULT_WINDOW_SIZE:
          backoff = DEFAULT_WINDOW_SIZE
    return results

  def _SaveAggregateData(self, aggregate_data):
    """Permanently store aggregate data to Titan Files."""
    window = aggregate_data['window']
    window_datetime = datetime.datetime.utcfromtimestamp(window)
    for counter_name, counter_value in aggregate_data['counters'].iteritems():
      path = _MakeLogPath(window_datetime, counter_name)
      file_obj = files.Get(path)
      content = []
      if file_obj:
        content = json.loads(file_obj.content)
      content.append((window, counter_value))

      date = datetime.datetime.utcfromtimestamp(window)
      # Strip hours/minutes/seconds from date since the datastore can only
      # store datetime objects, but we only need the date itself.
      date = datetime.datetime(date.year, date.month, date.day)
      meta = {
          'stats_counter_name': counter_name,
          'stats_date': date,
      }
      files.Write(path, content=json.dumps(content), meta=meta)

class CountersService(object):
  """A service class to retrieve permanently stored counter stats."""

  def GetCounterData(self, counter_names, start_date=None, end_date=None):
    """Get a date range of stored counter data.

    Args:
      counter_names: An iterable of counter names.
      start_date: A datetime.date object. Defaults to the current day.
      end_date: A datetime.date object. Defaults to current day.
    Returns:
      A dictionary mapping counter_names to a list of counter data. For example:
      {
          'page/view': [(<window>, <value>), (<window>, <value>), ...],
      }
    """
    if end_date and end_date < start_date:
      raise ValueError('End time %s must be greater than start time %s'
                       % (end_date, start_date))
    now = datetime.datetime.now()
    if not start_date:
      start_date = now
    if not end_date:
      end_date = now

    # Convert to datetime objects for the queries:
    start_date = datetime.datetime(
        start_date.year, start_date.month, start_date.day)
    end_date = datetime.datetime(
        end_date.year, end_date.month, end_date.day)

    # Get all files within the range.
    file_objs = []
    for counter_name in counter_names:
      filters = [
          ('stats_counter_name =', counter_name),
          ('stats_date >=', start_date),
          ('stats_date <=', end_date),
      ]
      new_file_objs = files.ListFiles(BASE_DIR, recursive=True, filters=filters)
      file_objs.extend(new_file_objs)

    final_counter_data = {}
    for file_obj in files.SmartFileList(file_objs):
      # Since JSON only represents lists, convert each inner-list back
      # to a two-tuple.
      counter_data = json.loads(file_obj.content)
      counter_data = [tuple(d) for d in counter_data]

      _, counter_name = _ParseLogPath(file_obj.path)
      if not counter_name in final_counter_data:
        final_counter_data[counter_name] = []
      final_counter_data[counter_name].extend(counter_data)
    return final_counter_data

def _GetWindow(timestamp=None, window_size=DEFAULT_WINDOW_SIZE):
  """Get the aggregation window for the given unix time and window size."""
  return int(window_size * round(float(timestamp) / window_size))

def _MakeLogPath(date, counter_name):
  # Make a path like: /_titan/stats/counters/2015/05/15/page/view/data-10s.json
  path = os.path.join(
      BASE_DIR, str(date.year), str(date.month), str(date.day),
      counter_name, DATA_FILENAME)
  return path

def _ParseLogPath(path):
  parts = path.split('/')
  date = datetime.date(int(parts[4]), int(parts[5]), int(parts[6]))
  counter_name = '/'.join(parts[7:-1])
  return date, counter_name
