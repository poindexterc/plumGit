from django.http import HttpResponse
from django.template import loader, Context

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


def pusherPushData(idNum, actionType, lineLocation = None, dataLocation = None, dataChange=None):
    try:
        p['%s'%str(idNum)].trigger('dataPush', {"Type": actionType, "LineFrom": lineStart, "LineTo": lineEnd, "CharFrom":charStart, "CharTo":charEnd, "ChangeTo": dataChange})
        debugPrint("Change Pushed: ID=%s TYPE=%s LINESTART=%s LINEEND=%s CHARSTART=%s CHAREND=%s CHANGE=%s" % (idNum, actionType, lineStart, lineEnd, charStart, charEnd, dataChange))
    except e:
        print("! Unexpected error:", sys.exc_info()[0])