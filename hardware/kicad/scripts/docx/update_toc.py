import os, sys, time
import officehelper
from com.sun.star.beans import PropertyValue


def prop(name, value):
    p = PropertyValue()
    p.Name = name
    p.Value = value
    return p


def url(path):
    return "file:///" + os.path.abspath(path).replace("\\", "/").replace(" ", "%20")


def refresh(path):
    ctx = officehelper.bootstrap()
    smgr = ctx.getServiceManager()
    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL(url(path), "_blank", 0, (prop("Hidden", True),))
    try:
        doc.getTextFields().refresh()
        try:
            doc.refresh()
        except Exception:
            pass
        idx = doc.getDocumentIndexes()
        for _ in range(2):
            for i in range(idx.getCount()):
                idx.getByIndex(i).update()
            time.sleep(0.4)
        doc.store()
        print("OK  " + os.path.basename(path))
    finally:
        doc.close(False)


for p in sys.argv[1:]:
    refresh(p)
