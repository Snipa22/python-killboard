from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, json, jsonify
import ConfigParser
import psycopg2
import psycopg2.extras
from datetime import datetime
import pylibmc

config = ConfigParser.ConfigParser()
config.read(['frontend.conf', 'local_frontend.conf'])
dbhost = config.get('Database', 'dbhost')
dbname = config.get('Database', 'dbname')
dbuser = config.get('Database', 'dbuser')
dbpass = config.get('Database', 'dbpass')
dbport = config.get('Database', 'dbport')
mckey = config.get('Memcache', 'key')
mcserver = config.get('Memcache', 'server')

app = Flask(__name__)
app.config.from_object(__name__)

@app.route('/')
def home():
    content = {
        "title": "Killboard Home",
        "topkills": {
            "1": {
                "pilotid": 1,
                "pilotname": "data",
                "shipid": 2,
                "shipname": "capsule"
            }
        },
        "topcapsules": {
            "1": {
                "pilotid": 1,
                "pilotname": "data",
            }
        },
        "date": datetime.utcnow().strftime("%A, %d. %B %Y %I:%M%p")
    }
    return render_template('index.tmpl', content=content)

@app.route('/pilot')
@app.route('/pilot/<name>')
def pilot(name=None):
    return

@app.route('/ship')
@app.route('/ship/<name>')
def ship(name=None):
    return

@app.route('/kill')
@app.route('/kill/<id>')
def kill(id=None):
    return

@app.route('/api')
@app.route('/api/<name>')
@app.route('/api/<name>/<value>')
def api(name=None, value=None):
    if name == None:
        return render_template('apiusage.html')
    curs = g.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    retVal = {'apiVersion': .1}
    name = name.lower()
    if value == None:
        value = 0
    try:
        value = int(value)
    except ValueError:
        value = 0
    if name == "killfp":
        curs.execute("""select * from killlist where killid > %s order by killid desc limit 10""", (value,))
        i = 1
        retVal['kills'] = {}
        for kill in curs:
            i += 1
            system = systemInfo(kill['systemid'])
            retVal['kills'][i] = {
                "loss": {},
                "fb": {},
                "killID": kill['killid'],
                "system": system['name'],
                "region": system['regionName'],
                "secstatus": system['secStatus'],
                "hours": kill['time'].strftime("%H:%M")
            }
            intcurs = g.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
            intcurs.execute("""select * from killvictim where killid = %s""", (kill['killid'],))
            victim = intcurs.fetchone()
            victimShip = itemMarketInfo(victim['shiptypeid'])
            retVal['kills'][i]['loss'] = {
                "corpID": victim['corporationid'],
                "corpName": victim['corporationname'],
                "itemName": victimShip['itemName'],
                "groupID": victimShip['groupID'],
                "groupName": victimShip['groupName'],
                "charID": victim['characterid'],
                "charName": victim['charactername'],
                "itemID": victim['shiptypeid']
            }
            intcurs.execute("""select * from killattackers where killid = %s AND finalblow = %s""",
                (kill['killid'], True))
            attacker = intcurs.fetchone()
            retVal['kills'][i]['fb'] = {
                "itemID": attacker['shiptypeid'],
                "charID": attacker['characterid'],
                "charName": attacker['charactername'],
                "corpID": attacker['corporationid'],
                "corpName": attacker['corporationname']
            }
            intcurs.execute("""select count(characterid) from killattackers where killid = %s""", 
                (kill['killid'],))
            killers = intcurs.fetchone()
            retVal['kills'][i]['numkillers'] = killers[0]
    elif name == "kill":
        if value == 0:
            retVal['error'] = "1"
            return jsonify(retVal)
    else:
        return render_template('apiusage.html')


    return jsonify(retVal)



def systemInfo(sysID):
    """Takes a system's ID, and gets name, regionID, regionName, secStatus, caches it"""
    systemID = int(sysID)
    try:
        retVal = g.mc.get(mckey + "sysid" + str(sysID))
        if retVal == None:
            raise pylibmc.Error()
    except (pylibmc.Error):
        curs = g.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        curs.execute("""select mapsolarsystems.regionid, mapsolarsystems.solarsystemid, mapsolarsystems.solarsystemname, 
            mapsolarsystems.security, mapregions.regionname from mapsolarsystems, mapregions where mapsolarsystems.regionid
            = mapregions.regionid and mapsolarsystems.solarsystemid = %s""", (systemID,))
        data = curs.fetchone()
        retVal = {"name": data['solarsystemname'], "regionID": data['regionid'], "regionName": data['regionname'], "secStatus": '%.1f' % round(data['security'], 1)}
        g.mc.set(mckey + "sysid" + str(sysID), retVal)
    return retVal

def itemMarketInfo(itemID):
    """Takes an item's typeID, gets groupName, groupID, Name, returns as a dict, cached of course."""
    typeID = int(itemID)
    
    try:
        g.mc.set(mckey + "typeid" + str(typeID), None)
        retVal = g.mc.get(mckey + "typeid" + str(typeID))
        if retVal == None:
            raise pylibmc.Error()
    except (pylibmc.Error):
        curs = g.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        curs.execute("""select invtypes.typename, invtypes.groupid, invgroups.groupname from invtypes, invgroups
            where invtypes.groupid = invgroups.groupid and invtypes.typeid = %s""", (typeID,))
        data = curs.fetchone()
        if typeID == 670:
            retVal = {"itemName": "Capsule", "groupID": "0", "groupName": "Capsule"}
        else:
            retVal = {"itemName": data['typename'], "groupID": data['groupid'], "groupName": data['groupname']}
        g.mc.set(mckey + "typeid" + str(typeID), retVal)
    return retVal


def connect_db():
    if not dbpass:
    # Connect without password
        return psycopg2.connect("host="+dbhost+" user="+dbuser+" dbname="+dbname+" port="+dbport)
    else:
        return psycopg2.connect("host="+dbhost+" user="+dbuser+" password="+dbpass+" dbname="+dbname+" port="+dbport)

@app.before_request
def before_request():
    g.db = connect_db()
    g.staticContent = config.get('URLs', 'staticFiles')
    g.staticImages = config.get('URLs', 'staticImages')
    g.mc = pylibmc.Client([mcserver], binary=True, behaviors={"tcp_nodelay": True, "ketama": True})

@app.teardown_request
def teardown_request(exception):
    g.db.close()

if __name__ == '__main__':
    app.debug = True
    app.run(port=8084)
