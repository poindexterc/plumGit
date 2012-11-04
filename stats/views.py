from django.http import HttpRequest, HttpResponse
from titan.stats import stats

def process_data(request):
    """
    @type request: WSGIRequest
    """
    all_counters = [
        stats.Counter('log_starts'),
        stats.Counter('application_starts'),
        ]

    aggregator = stats.Aggregator(all_counters)

    # check to see if this was run via cron handler:
    #    X-AppEngine-Cron: true
    development = False
#    if not request.meta.get("X-AppEngine-Cron"):
#        development = True

    # Pull task queue tasks, aggregate their data, and save it permanently in Titan Files.
    aggregator.ProcessWindowsWithBackoff(total_runtime_minutes=1, development=development)

    return HttpResponse("ok")
