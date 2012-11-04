import random
import pusher
import sys

pusher.app_id = '30052'
pusher.key = '8754603d024bc6ca00de'
pusher.secret = '785335c8057c784eccb0'
p = pusher.Pusher()

def pusherPushData(idNum, actionType, lineStart = None, lineEnd = None, charStart = None, charEnd = None, dataChange=None):
    p['%s'%idNum].trigger('dataPush', {"Type": actionType, "LineFrom": lineStart, "LineTo": lineEnd, "CharFrom":charStart, "CharTo":charEnd, "ChangeTo": dataChange})

    print("Change Pushed: ID=%s TYPE=%s LINESTART=%s LINEEND=%s CHARSTART=%s CHAREND=%s CHANGE=%s" % (idNum, actionType, lineStart, lineEnd, charStart, charEnd, dataChange))


def main():
    inputdata = ""
    while inputdata != "q":
        inputdata = raw_input("- Press enter to send pusher data - ")
        if inputdata != "q":
            alpha = ["a", "b", "c"]
            pusherPushData("testchannel", "addChar", 2, 2, random.randint(20,29), random.randint(30,39), "def monil_is_gettin_it_it_wit_liz(): \n")



main()
