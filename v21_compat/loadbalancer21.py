import sys
import anki
import aqt
from aqt import mw
from anki.sched import Scheduler


def lbDbg(s, level):
    if qc["debugLevel"] >= level:
        print(s)


# the scheduling function
OLD_adjRevIvl = anki.sched.Scheduler._adjRevIvl


def NEW_adjRevIvl(self, card, idealIvl):

    # Hiding.  I care not if what Gnome did was evil.
    LBWorkload = 0.8

    idealIvl = int(idealIvl)

    lbDbg("id= " + str(card.id) + " ivl=" + str(idealIvl), 1)

    ivlmin = idealIvl - min(qc["MaxDaysBefore"], int(idealIvl * qc["PercentBefore"]))
    ivlmax = idealIvl + min(qc["MaxDaysAfter"], int(idealIvl * qc["PercentAfter"]))
    ivlmin = max(min(ivlmin, idealIvl - qc["MinDaysBefore"]), 1)
    ivlmax = max(ivlmax, idealIvl + qc["MinDaysAfter"])

    maxdue = 1.0
    mindue = (0xFFFFFFFF) * 1.0
    maxease = 0.0
    minease = (0xFFFFFFFF) * 1.0
    cardsdue = []
    ivlrange = range(ivlmin, ivlmax + 1)
    for i in ivlrange:
        due = self.today + i
        siblings = self.col.db.scalar('''select count() from cards where due = ? and nid = ? and queue = 2''',
                                      due, card.nid)
        if siblings:
            sibling = True
        else:
            sibling = False

        # Wether to schedule by each deck load or the load of all the decks
        if qc["SchedulePerDeck"]:
            cds = self.col.db.all('''select factor from cards where due = ? and did = ? and queue = 2''', due, card.did)
        else:
            cds = self.col.db.all('''select factor from cards where due = ? and queue = 2''', due)

        maxdue = max(maxdue, len(cds) * 1.0)
        mindue = min(mindue, len(cds) * 1.0)

        ease = 0
        for c in cds:
            ease += c[0]
        if cds:
            ease /= len(cds)
        ease /= 10.0

        maxease = max(maxease, ease)
        minease = min(minease, ease)

        cardsdue.append([i, len(cds), ease, sibling])

    lowest = cardsdue[0]
    for c in cardsdue:
        if maxdue == mindue:
            workload = 1
        else:
            workload = (c[1] - mindue) / (maxdue - mindue)
        if c[1] == 0:
            rease = 0
        else:
            if maxease == minease:
                rease = 1
            else:
                rease = (maxease - c[2]) / (maxease - minease)

        compease = LBWorkload * workload + (1-LBWorkload) * rease
        lbDbg("%3d: %.2f*%.4f + %.2f*%.4f = %.4f" % (c[0], LBWorkload, workload, 1-LBWorkload, rease, compease), 1)

        if c[3] == True:
            compease += 1
        c.insert(3, compease)

        if lowest[3] > c[3]:
            lowest = c

    for c in cardsdue:
        if c[0] == lowest[0]:
            if c[4] == True:
                lbDbg("x%3d, %3d, %4.1f, %1.4f" % tuple(c[:4]), 1)
            else:
                lbDbg("*%3d, %3d, %4.1f, %1.4f" % tuple(c[:4]), 1)
        else:
            if c[4] == True:
                lbDbg("s%3d, %3d, %4.1f, %1.4f" % tuple(c[:4]), 1)
            else:
                lbDbg(" %3d, %3d, %4.1f, %1.4f" % tuple(c[:4]), 1)

    # lbDbg("LB Out: " + str(card.id) + " ivl=" + str(lowest[0]), 2)

    return lowest[0]


anki.sched.Scheduler._adjRevIvl = NEW_adjRevIvl


# get lapsed->review cards
OLD_rescheduleAsRev = anki.sched.Scheduler._rescheduleAsRev


def NEW_rescheduleAsRev(self, card, conf, early):
    lapse = card.type == 2
    OLD_rescheduleAsRev(self, card, conf, early)
    if lapse:
        lbDbg("Lapse: yes", 1)
        card.ivl = NEW_adjRevIvl(self, card, card.ivl)
        card.due = self.today+card.ivl
    else:
        lbDbg("Lapse: no", 1)


anki.sched.Scheduler._rescheduleAsRev = NEW_rescheduleAsRev

qc = mw.addonManager.getConfig(__name__)
lbDbg(qc, 1)
