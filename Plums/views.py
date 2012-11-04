# following two imports are for accessing Blobstore blobs like files
from __future__ import with_statement
from google.appengine.api import files
from google.appengine.ext import blobstore

import fix_settings
from unittest.suite import TestSuite
from google.appengine.api.taskqueue.taskqueue import TransientError
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, HttpResponseForbidden, Http404
from django.shortcuts import render_to_response
from django.utils import simplejson
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.template import RequestContext
from django.conf import settings

from django.core.urlresolvers import reverse
from djangoappengine.utils import on_production_server, have_appserver
from google.appengine.api import namespace_manager
from google.appengine.api import taskqueue
from google.appengine.api import memcache
from google.appengine.ext import deferred
from google.appengine.api import channel
from google.appengine.api import users
from google.appengine.api import mail
from google.appengine.api import urlfetch
from google.appengine.api import app_identity
from google.appengine.ext import ndb

from google.appengine.runtime import DeadlineExceededError

from random import randint
from uuid import uuid4
import logging
import re
import hashlib
import math
import calendar
import unittest
import Cookie
import StringIO
import csv
from time import mktime
from operator import itemgetter
import locale
import urllib
import lib.pytz as pytz
from time import gmtime, strftime

from datetime import *
from sys import exc_info


import pusher
import sys

debug = True
pusher.app_id = '30052'
pusher.key = '8754603d024bc6ca00de'
pusher.secret = '785335c8057c784eccb0'
p = pusher.Pusher()


def debugPrint(astring):
    if debug:
        print debug




def home(request, template):

    response = render_to_response(template, dictionary={"h": "i"}, context_instance=RequestContext(request))
    return response


def pusherPushData(idNum, actionType, lineLocation = None, dataLocation = None, dataChange=None):
    try:
        p['%s'%str(idNum)].trigger('dataPush', {"Type": actionType, "LineFrom": lineStart, "LineTo": lineEnd, "CharFrom":charStart, "CharTo":charEnd, "ChangeTo": dataChange})
        debugPrint("Change Pushed: ID=%s TYPE=%s LINESTART=%s LINEEND=%s CHARSTART=%s CHAREND=%s CHANGE=%s" % (idNum, actionType, lineStart, lineEnd, charStart, charEnd, dataChange))
    except e:
        print("! Unexpected error:", sys.exc_info()[0])