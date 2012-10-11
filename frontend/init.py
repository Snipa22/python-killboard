from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, json, jsonify
import ConfigParser
import psycopg2
from datetime import datetime

config = ConfigParser.ConfigParser()
config.read(['frontend.conf', 'local_frontend.conf'])
dbhost = config.get('Database', 'dbhost')
dbname = config.get('Database', 'dbname')
dbuser = config.get('Database', 'dbuser')
dbpass = config.get('Database', 'dbpass')
dbport = config.get('Database', 'dbport')

app = Flask(__name__)
app.config.from_object(__name__)

@app.route('/api')
@app.route('/api/<name>')
@app.route('/api/<name>/<value>')
def api(name=None, value=None):
    if name == None:
        return render_template('apiusage.html')
    curs = g.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    retVal = {'apiVersion': .1}
    name = name.lower()
    value = int(value)
    if name == "killfp":
        curs.execute("""select * from "killList" where "killID" > %s order by "killID" desc limit 10""", (value,))
        i = 0
        retVal['kills'] = {}
        for kill in curs:
            i++
            system = systemInfo(kill['systemID'])
            retVal['kills'][i] = {}
            retVal['kills'][i]['loss'] = {}
            retVal['kills'][i]['fb'] = {}
            retVal['kills'][i]['killID'] = kill['killID']
            retVal['kills'][i]['system'] = system['name']
            retVal['kills'][i]['region'] = system['regionName']
            retVal['kills'][i]['secstatus'] = system['secstatus']
            retVal['kills'][i]['hours'] = kill['time'].strftime("%H:%M")
            intcurs = g.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
            intcurs.execute("""select * from "killVictim" where "killID" = %s""", (kill['killID'],))
            victim = intcurs.fetchone()
            victimShip = itemMarketInfo(victim['shipTypeID'])
            retVal['kills'][i]['loss']['corpID'] = victim['corporationID']
            retVal['kills'][i]['loss']['corpName'] = victim['corporationName']
            retVal['kills'][i]['loss']['itemName'] = victimShip['itemName']
            retVal['kills'][i]['loss']['groupID'] = victimShip['groupID']
            retVal['kills'][i]['loss']['groupName'] = victimShip['GroupName']
            retVal['kills'][i]['loss']['charID'] = victim['characterID']
            retVal['kills'][i]['loss']['charName'] = victim['characterName']
            retVal['kills'][i]['loss']['itemID'] = victim['shipTypeID']
            intcurs.execute("""select * from "killVictim" where "killID" = %s AND "finalBlow" = %s""",
                (kill['killID'], True))
            attacker = intcurs.fetchone()
            retVal['kills'][i]['fb']['itemID'] = attacker['shipTypeID']
            retVal['kills'][i]['fb']['charID'] = attacker['characterID']
            retVal['kills'][i]['fb']['charName'] = attacker['characterName']
            retVal['kills'][i]['fb']['corpID'] = attacker['corporationID']
            retVal['kills'][i]['fb']['corpName'] = attacker['characterName']
            intcurs.execute("""select count("characterID") from killVictim" where "killID" = %s""", 
                (kill['killID'],))
            retVal['kills'][i]['numkillers'] = int(intcurs.fetchone())
    return jsonify(retVal)

def systemInfo(sysID):
    """Takes a system's ID, and gets name, regionID, regionName, secStatus, caches it"""
    return

def itemMarketInfo(itemID):
    """Takes an item's typeID, gets groupName, groupID, Name, returns as a dict, cached of course."""
    return


def connect_db():
    if not dbpass:
    # Connect without password
        return psycopg2.connect("host="+dbhost+" user="+dbuser+" dbname="+dbname+" port="+dbport)
    else:
        return psycopg2.connect("host="+dbhost+" user="+dbuser+" password="+dbpass+" dbname="+dbname+" port="+dbport)

@app.before_request
def before_request():
    g.db = connect_db()
    g.staticImages = config.get('URLs', 'staticImages')

@app.teardown_request
def teardown_request(exception):
    g.db.close()

if __name__ == '__main__':
    app.run()
