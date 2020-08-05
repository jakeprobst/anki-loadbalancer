import anki
import aqt
import aqt.preferences
import aqt.deckconf
from anki.hooks import wrap
from anki.sched import Scheduler
import anki.stats
from aqt.qt import *
from PyQt5 import QtCore, QtGui, QtWidgets
import math
from bs4 import BeautifulSoup

def p(s=''):
    pass
    #print(s.encode('utf-8'))

# the scheduling function

OLD_adjRevIvl = anki.sched.Scheduler._adjRevIvl

def NEW_adjRevIvl(self, card, idealIvl):
    qc = self.col.conf
    conf = self.col.decks.confForDid(card.did)
    if conf['dyn']:
        conf = self.col.decks.confForDid(card.odid)

    idealIvl = int(idealIvl)

    normal = True
    if card.queue == 1: # new cards
        nc = conf['new']
        gi = nc['ints'][0]
        ei = nc['ints'][1]

        if gi == idealIvl:
            if "LBGIMinBefore" in nc and -1 not in [nc["LBGIMinBefore"], nc["LBGIMinAfter"]]:
                ivlmin = max(nc["LBGIMinBefore"], 1)
                ivlmax = nc["LBGIMinAfter"]
                normal = False
        elif ei == idealIvl:
            if "LBEIMinBefore" in nc and -1 not in [nc["LBEIMinBefore"], nc["LBEIMinAfter"]]:
                ivlmin = max(nc["LBEIMinBefore"], 1)
                ivlmax = nc["LBEIMinAfter"]
                normal = False
    if normal:
        ivlmin = idealIvl - min(qc["LBMaxBefore"], int(idealIvl*qc["LBPercentBefore"])) 
        ivlmax = idealIvl + min(qc["LBMaxAfter"], int(idealIvl*qc["LBPercentAfter"]))
        ivlmin = max(min(ivlmin, idealIvl-qc["LBMinBefore"]), 1)
        ivlmax = max(ivlmax, idealIvl+qc["LBMinAfter"])

    maxdue = 1.0
    mindue = (0xFFFFFFFF)*1.0
    maxease = 0.0
    minease = (0xFFFFFFFF)*1.0
    cardsdue = []
    ivlrange = list(range(ivlmin, ivlmax+1))
    for i in ivlrange:
        due = self.today + i
        siblings = self.col.db.scalar('''select count() from cards where due = ? and nid = ? and queue = 2''', 
                                      due, card.nid)
        if siblings:
            sibling = True
        else:
            sibling = False

        # Wether to schedule by each deck load or the load of all the decks
        if qc["LBDeckScheduling"]:
            cds = self.col.db.all('''select factor from cards where due = ? and did = ? and queue = 2''', due, card.did)
        else:
            cds = self.col.db.all('''select factor from cards where due = ? and queue = 2''', due)

        maxdue = max(maxdue, len(cds)*1.0)
        mindue = min(mindue, len(cds)*1.0)

        ease = 0
        for c in cds:
            ease += c[0]
        if cds:
            ease /= len(cds)
        ease /= 10.0

        maxease = max(maxease, ease)
        minease = min(minease, ease)

        cardsdue.append([i, len(cds), ease, sibling])
    
    p(BeautifulSoup(card.render_output().question_text, "html.parser").getText())
    lowest = cardsdue[0]
    for c in cardsdue:
        if maxdue == mindue:
            workload = 1
        else:
            workload = (c[1]-mindue)/(maxdue-mindue)
        if c[1] == 0:
            rease = 0
        else:
            if maxease == minease:
                rease = 1
            else:
                rease = (maxease-c[2])/(maxease-minease)


        compease = qc["LBWorkload"]*workload + (1-qc["LBWorkload"])*rease
        p("%3d: %.2f*%.4f + %.2f*%.4f = %.4f" % (c[0], qc["LBWorkload"], workload, 1-qc["LBWorkload"], 
                                                 rease, compease))
        if c[3] == True:
            compease += 1
        c.insert(3, compease)

        if lowest[3] > c[3]:
            lowest = c 
    
    for c in cardsdue:
        if c[0] == lowest[0]:
            if c[4] == True:
                p("x%3d, %3d, %4.1f, %1.4f" % tuple(c[:4]))
            else:
                p("*%3d, %3d, %4.1f, %1.4f" % tuple(c[:4]))
        else:
            if c[4] == True:
                p("s%3d, %3d, %4.1f, %1.4f" % tuple(c[:4]))
            else:
                p(" %3d, %3d, %4.1f, %1.4f" % tuple(c[:4]))
    p()
    return lowest[0]

anki.sched.Scheduler._adjRevIvl = NEW_adjRevIvl


# get lapsed->review cards

OLD_rescheduleAsRev = anki.sched.Scheduler._rescheduleAsRev

def NEW_rescheduleAsRev(self, card, conf, early):
    lapse = card.type == 2
    OLD_rescheduleAsRev(self, card, conf, early)
    if lapse:
        card.ivl = NEW_adjRevIvl(self, card, card.ivl)
        card.due = self.today+card.ivl

anki.sched.Scheduler._rescheduleAsRev = NEW_rescheduleAsRev


# preference menu stuff

def NEWsetupUi(self, Preferences):
    self.lbtab = QtWidgets.QWidget()
    self.lbvl = QtWidgets.QGridLayout(self.lbtab)
    self.lbvl.setColumnStretch(0, 0)
    self.lbvl.setColumnStretch(1, 0)
    self.lbvl.setColumnStretch(2, 0)
    self.lbvl.setColumnStretch(3, 1)

    row = 0
    general = QtWidgets.QLabel("<b>Adjust range</b>")
    self.lbvl.addWidget(general, row, 0, 1, 3)
    row += 1

    daybef = QtWidgets.QLabel("Days before")
    daybef.setToolTip("check [interval*percent] days before scheduled day")
    self.lbperb = QtWidgets.QSpinBox(self.lbtab)
    per1 = QtWidgets.QLabel("percent")
    self.lbvl.addWidget(daybef, row, 0)
    self.lbvl.addWidget(self.lbperb, row, 1)
    self.lbvl.addWidget(per1, row, 2)
    row += 1

    dayaft = QtWidgets.QLabel("Days after")
    dayaft.setToolTip("check [interval*percent] days after scheduled day")
    self.lbpera = QtWidgets.QSpinBox(self.lbtab)
    per2 = QtWidgets.QLabel("percent")
    self.lbvl.addWidget(dayaft, row, 0)
    self.lbvl.addWidget(self.lbpera, row, 1)
    self.lbvl.addWidget(per2, row, 2)
    row += 1

    maxdbe = QtWidgets.QLabel("Max time before")
    maxdbe.setToolTip("Maximum number of days to check before scheduled day")
    self.lbmaxb = QtWidgets.QSpinBox(self.lbtab)
    day1 = QtWidgets.QLabel("days")
    self.lbvl.addWidget(maxdbe, row, 0)
    self.lbvl.addWidget(self.lbmaxb, row, 1)
    self.lbvl.addWidget(day1, row, 2)
    row += 1

    maxdaf = QtWidgets.QLabel("Max time after")
    maxdaf.setToolTip("Maximum number of days to check after scheduled day")
    self.lbmaxa = QtWidgets.QSpinBox(self.lbtab)
    day2 = QtWidgets.QLabel("days")
    self.lbvl.addWidget(maxdaf, row, 0)
    self.lbvl.addWidget(self.lbmaxa, row, 1)
    self.lbvl.addWidget(day2, row, 2)
    row += 1

    mindbe = QtWidgets.QLabel("Min time before")
    mindbe.setToolTip("Minimum number of days to check before scheduled day")
    self.lbminb = QtWidgets.QSpinBox(self.lbtab)
    day3 = QtWidgets.QLabel("days")
    self.lbvl.addWidget(mindbe, row, 0)
    self.lbvl.addWidget(self.lbminb, row, 1)
    self.lbvl.addWidget(day3, row, 2)
    row += 1

    mindaf = QtWidgets.QLabel("Min time after")
    mindaf.setToolTip("Minimum number of days to check after scheduled day")
    self.lbmina = QtWidgets.QSpinBox(self.lbtab)
    day4 = QtWidgets.QLabel("days")
    self.lbvl.addWidget(mindaf, row, 0)
    self.lbvl.addWidget(self.lbmina, row, 1)
    self.lbvl.addWidget(day4, row, 2)
    row += 1

    easehead = QtWidgets.QLabel("<b>Ease balancing</b>")
    self.lbvl.addWidget(easehead, row, 0, 1, 3)
    row += 1

    wotol = QtWidgets.QLabel("Workload:Ease")
    wotol.setToolTip("Ratio to value amount due over the average easiness in a day when scheduling.")
    self.lbwl = QtWidgets.QSpinBox(self.lbtab)
    self.lbwl2 = QtWidgets.QSpinBox(self.lbtab)
    self.lbwl.valueChanged[int].connect(lambda k: self.lbwl2.setValue(100-k))
    self.lbwl2.valueChanged[int].connect(lambda k: self.lbwl.setValue(100-k))
    self.lbwl.setMaximum(100)
    self.lbwl2.setMaximum(100)
    self.lbvl.addWidget(wotol, row, 0)
    self.lbvl.addWidget(self.lbwl, row, 1)
    self.lbvl.addWidget(self.lbwl2, row, 2)
    row += 1

    otherhead = QtWidgets.QLabel("<b>Other</b>")
    self.lbvl.addWidget(otherhead, row, 0, 1, 3)
    row += 1

    self.lbds = QtWidgets.QCheckBox("Schedule based on each deck load", self.lbtab)
    self.lbds.setToolTip("Whether to schedule based on each deck load or the load of all decks.")
    self.lbvl.addWidget(self.lbds, row, 0)
    row += 1

    spacer = QtWidgets.QSpacerItem(1, 1, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
    self.lbvl.addItem(spacer, row, 0)

    self.tabWidget.addTab(self.lbtab, "Load Balancer")

def NEW__init__(self, mw):
    qc = self.mw.col.conf
    self.form.lbperb.setValue(qc["LBPercentBefore"]*100)
    self.form.lbpera.setValue(qc["LBPercentAfter"]*100)
    self.form.lbmaxb.setValue(qc["LBMaxBefore"])
    self.form.lbmaxa.setValue(qc["LBMaxAfter"])
    self.form.lbminb.setValue(qc["LBMinBefore"])
    self.form.lbmina.setValue(qc["LBMinAfter"])

    self.form.lbwl.setValue(qc["LBWorkload"]*100)
    self.form.lbds.setChecked(qc["LBDeckScheduling"])

def NEWaccept(self):
    qc = self.mw.col.conf
    qc["LBPercentBefore"] = self.form.lbperb.value()/100.0
    qc["LBPercentAfter"]  = self.form.lbpera.value()/100.0
    qc["LBMaxBefore"]     = self.form.lbmaxb.value()
    qc["LBMaxAfter"]      = self.form.lbmaxa.value()
    qc["LBMinBefore"]     = self.form.lbminb.value()
    qc["LBMinAfter"]      = self.form.lbmina.value()

    qc["LBWorkload"]      = self.form.lbwl.value()/100.0
    qc["LBDeckScheduling"]      = self.form.lbds.isChecked()

aqt.forms.preferences.Ui_Preferences.setupUi = wrap(aqt.forms.preferences.Ui_Preferences.setupUi, 
                                                    NEWsetupUi, pos="after")
aqt.preferences.Preferences.__init__ = wrap(aqt.preferences.Preferences.__init__, NEW__init__, pos="after")
aqt.preferences.Preferences.accept = wrap(aqt.preferences.Preferences.accept, NEWaccept, pos="before")


# deck menu stuff

def NEWdconfsetupUi(self, Dialog):
    srow = 7
    agi = QtWidgets.QLabel("<b>Load Balance</b>")
    self.gridLayout.addWidget(agi, srow, 0, 1, 3)
    srow += 1

    agi = QtWidgets.QLabel("<b>&nbsp;&nbsp;&nbsp;&nbsp;Graduating interval</b>")
    self.gridLayout.addWidget(agi, srow, 0, 1, 3)
    srow += 1

    gimtb = QtWidgets.QLabel("Minimum")
    gimtb.setToolTip("Minimum number of days to check after scheduled day\n-1 disables")
    self.lbgiminb = QtWidgets.QSpinBox()
    self.lbgiminb.setMinimum(-1)
    day5 = QtWidgets.QLabel("days")
    self.gridLayout.addWidget(gimtb, srow, 0)
    self.gridLayout.addWidget(self.lbgiminb, srow, 1)
    self.gridLayout.addWidget(day5, srow, 2)
    srow += 1

    gimta = QtWidgets.QLabel("Maximum")
    gimta.setToolTip("Minimum number of days to check after scheduled day\n-1 disables")
    self.lbgimina = QtWidgets.QSpinBox()
    self.lbgimina.setMinimum(-1)
    day6 = QtWidgets.QLabel("days")
    self.gridLayout.addWidget(gimta, srow, 0)
    self.gridLayout.addWidget(self.lbgimina, srow, 1)
    self.gridLayout.addWidget(day6, srow, 2)
    srow += 1
    
    aei = QtWidgets.QLabel("<b>&nbsp;&nbsp;&nbsp;&nbsp;Easy interval</b>")
    self.gridLayout.addWidget(aei, srow, 0, 1, 3)
    srow += 1

    eimtb = QtWidgets.QLabel("Minimum")
    eimtb.setToolTip("Minimum number of days to check after scheduled day\n-1 disables")
    self.lbeiminb = QtWidgets.QSpinBox()
    self.lbeiminb.setMinimum(-1)
    day7 = QtWidgets.QLabel("days")
    self.gridLayout.addWidget(eimtb, srow, 0)
    self.gridLayout.addWidget(self.lbeiminb, srow, 1)
    self.gridLayout.addWidget(day7, srow, 2)
    srow += 1

    eimta = QtWidgets.QLabel("Maximum")
    eimta.setToolTip("Minimum number of days to check after scheduled day\n-1 disables")
    self.lbeimina = QtWidgets.QSpinBox()
    self.lbeimina.setMinimum(-1)
    day8 = QtWidgets.QLabel("days")
    self.gridLayout.addWidget(eimta, srow, 0)
    self.gridLayout.addWidget(self.lbeimina, srow, 1)
    self.gridLayout.addWidget(day8, srow, 2)
    srow += 1

    self.lrnGradInt.setDisabled(True)
    self.lrnEasyInt.setDisabled(True)

def NEWloadConf(self):
    c = self.conf['new']
    f = self.form
    keys = {"LBGIMinBefore": 1,
            "LBGIMinAfter": 1,
            "LBEIMinBefore": 4,
            "LBEIMinAfter": 4}
    for k in keys:
        if k not in c:
            c[k] = keys[k]
    f.lbgiminb.setValue(c["LBGIMinBefore"])
    f.lbgimina.setValue(c["LBGIMinAfter"])
    f.lbeiminb.setValue(c["LBEIMinBefore"])
    f.lbeimina.setValue(c["LBEIMinAfter"])

def NEWsaveConf(self):
    c = self.conf['new']
    f = self.form
    c['LBGIMinBefore'] = f.lbgiminb.value()
    c['LBGIMinAfter'] = f.lbgimina.value()
    c['LBEIMinBefore'] = f.lbeiminb.value()
    c['LBEIMinAfter'] = f.lbeimina.value()


aqt.forms.dconf.Ui_Dialog.setupUi = wrap(aqt.forms.dconf.Ui_Dialog.setupUi, 
                                                    NEWdconfsetupUi, pos="after")
aqt.deckconf.DeckConf.loadConf = wrap(aqt.deckconf.DeckConf.loadConf, NEWloadConf, pos="after")
aqt.deckconf.DeckConf.saveConf = wrap(aqt.deckconf.DeckConf.saveConf, NEWsaveConf, pos="before")

# graph stuff

COLOR1 = "#654321"
COLOR2 = "#CBA987"
COLOR3 = "#432100"
COLOR4 = "#A98765"

OLDdueGraph = anki.stats.CollectionStats.dueGraph

def NEWdueGraph(self):
    qc = self.col.conf
    today = self.col.sched.today
    start = end = None
    chunk = 1
    if self.type == 0:
        start = 0; end = 31; chunk = 1
    elif self.type == 1:
        start = 0; end = 52; chunk = 7
    elif self.type == 2:
        start = 0; end = 12*10; chunk = 30 

    days = []
    maxdue = 1.0
    mindue = 0xFFFFFFFF*1.0
    maxldiff = 0.0
    minldiff = 0xFFFFFFFF*1.0
    for z in range(end):
        cds = self.col.db.all('''select factor from cards where ? <= due and due < ? and queue = 2 
                                 and did in %s''' % self._limit(), 
                                 today+(chunk*z), today+(chunk*(z+1)))
        if len(cds) > maxdue:
            maxdue = len(cds)*1.0
        if len(cds) < mindue:
            mindue = len(cds)*1.0
        if len(cds) == 0:
            days.append([0, 0])
            if self.type == 2: # cause a month with nothing is most likely the end
                break
            else:
                continue

        lease = 0
        for c in cds:
            lease += c[0]
        lease /= len(cds)

        #ldiff = 1000.0/lease # 1000 cause otherwise numbers are .000X and not useful to look at
        ldiff = lease/10.0
        if ldiff > maxldiff:
            maxldiff = ldiff
        if ldiff < minldiff:
            minldiff = ldiff
        
        days.append([len(cds), ldiff])

    if maxldiff == 0:
        maxldiff = 1

    d = 0
    diffs = []
    compdiffs = []
    for cd in days:
        try:
            wl = (cd[0]-mindue)/(maxdue-mindue)
        except ZeroDivisionError:
            wl = 1
        if cd[1] == 0:
            rdiff = 0
        else:
            try:
                rdiff = (maxldiff-cd[1])/(maxldiff-minldiff)
            except ZeroDivisionError:
                rdiff = 1
        diffs.append([d, wl*qc["LBWorkload"]*100])
        compdiffs.append([d, rdiff*(1-qc["LBWorkload"])*100])

        d += 1

    out = self._title("Difficulty Forecast", "The average difficulty of reviews in the future.")
    data = [dict(data=diffs, color=COLOR1, label="Due", stack=0), 
            dict(data=compdiffs, color=COLOR2, label="Ease", stack=0)]
    out += self._graph(id="fordiff", data=data, conf=dict(xaxis=dict(tickDecimals=0, min=-0.5), 
                                                          yaxis=dict(tickDecimals=0, max=100)), ylabel="%")

    #i = []
    #self._line(i, "Average Difficulty", "%.1f%%" % avgease)
    #self._line(i, "Average Compound Difficulty", "%.1f%%" % avgcomp)
    #out += self._lineTbl(i)

    return OLDdueGraph(self) + out

anki.stats.CollectionStats.dueGraph = NEWdueGraph


# initialization stuff

def InitConf(self, *args):
    qc = self.conf
    keys = {"LBPercentBefore": .1, 
            "LBPercentAfter": .1,
            "LBMaxBefore": 6, 
            "LBMaxAfter": 4,
            "LBMinBefore": 1,
            "LBMinAfter": 1,
            "LBWorkload": .8,
            "LBDeckScheduling": False
            }

    for k in keys:
        if k not in qc:
            qc[k] = keys[k]

    # cleanup no longer used config options
    delkeys = ["LBShuffle", "LBTolerance", "LBEaseBalance",
               "LBLowPercent"]
    for k in delkeys:
        if k in qc:
            del qc[k]

anki.collection._Collection.__init__ = wrap(anki.collection._Collection.__init__, InitConf, pos="after")




