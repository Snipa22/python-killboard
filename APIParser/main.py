import ConfigParser
import psycopg2
import psycopg2.extras
from hotqueue import HotQueue
import gevent
from gevent.pool import Pool
from gevent import monkey; gevent.monkey.patch_all()
import pylibmc
import logging
import eveapi
import urllib

config = ConfigParser.ConfigParser()
config.read(['api.conf', 'local_api.conf'])
dbhost = config.get('Database', 'dbhost')
dbname = config.get('Database', 'dbname')
dbuser = config.get('Database', 'dbuser')
dbpass = config.get('Database', 'dbpass')
dbport = config.get('Database', 'dbport')
redisdb = config.get('Redis', 'redishost')
apiServer = config.get('API', 'host')
mcserver = config.get('Memcache', 'server')
mckey = config.get('Memcache', 'key')
psource = config.get('Pricing', 'source')
ecapi = config.get('Pricing', 'echost')
e43api = config.get('Pricing', 'e43host')
psqlhost = config.get('Pricing', 'psqlhost')
psqlname = config.get('Pricing', 'psqlname')
psqluser = config.get('Pricing', 'psqluser')
psqlpass = config.get('Pricing', 'psqlpass')
psqlport = config.get('Pricing', 'psqlport')

MAX_NUM_POOL_WORKERS = 75

queue = HotQueue("killboard-API", host=redisdb, port=6379, db=0)

logging.basicConfig(format='%(asctime)s:%(levelname)s:%(message)s', level=logging.DEBUG)

# use a greenlet pool to cap the number of workers at a reasonable level
greenlet_pool = Pool(size=MAX_NUM_POOL_WORKERS)

def main():
    for message in queue.consume():
        greenlet_pool.spawn(worker, message)

def priceCheck(typeID):
    typeID = int(typeID)
    mc = pylibmc.Client([mcserver], binary=True, behaviors={"tcp_nodelay": True, "ketama": True})
    if mckey + "price" + str(typeID) in mc:
        return mc.get(mckey + "price" + str(typeID))
    # Handle DBs without password
    if not dbpass:
    # Connect without password
        pricedbcon = psycopg2.connect("host="+dbhost+" user="+dbuser+" dbname="+dbname+" port="+dbport)
    else:
        pricedbcon = psycopg2.connect("host="+dbhost+" user="+dbuser+" password="+dbpass+" dbname="+dbname+" port="+dbport)
    curs = pricedbcon.cursor()
    curs.execute("""select manual, override, api from prices where typeid = %s""", (typeID,))
    data = curs.fetchone()
    if data[0]:
        retVal = data[1]
    elif psource == "psql":
        retVal = psqlpricing(typeID)
    elif psource == "ec":
        retVal = retVal = ecpricing(typeID)
    elif psource == "e43api":
        pass
    else:
        retVal = ecpricing(typeID)
    if !retVal:
        retVal = data[2]
    elif retVal != 0:
        mc.set(mckey + "price" + str(typeID), retVal, 300)
        try:
            curs.execute("""update prices set api = %s where typeid = %s""", (retVal,typeID))
        except:
            curs.execute("""insert into prices (typeid, api) values (%s, %s)""", (typeID, retVal))
    return retVal

def psqlpricing(typeID):
    # Handle DBs without password
    if not dbpass:
    # Connect without password
        dbcon = psycopg2.connect("host="+psqlhost+" user="+psqluser+" dbname="+psqlname+" port="+psqlport)
    else:
        dbcon = psycopg2.connect("host="+psqlhost+" user="+psqluser+" password="+psqlpass+" dbname="+psqlname+" port="+psqlport)
    curs = dbcon.cursor(psycopg2.extras.DictCursor)
    curs.execute("""select * from market_data_itemregionstat where mapregion_id = 10000002 and invtype_id = %s """, (typeID,))
    data = curs.fetchone()
    if data['sell_95_percentile'] != 0:
        return data['sell_95_percentile']
    elif data['sellmedian'] != 0:
        return data['sellmedian']
    else:
        curs.execute("""select * from market_data_itemregionstathistory where mapregion_id = 10000002 and invtype_id = %s and (sellmedian != 0 or sell_95_percentile != 0) order by date desc limit 1""", (typeID,))
        data = curs.fetchone()
        if data['sell_95_percentile'] != 0:
            return data['sell_95_percentile']
        elif data['sellmedian'] != 0:
            return data['sellmedian']
    return False

def worker(message):
    # Handle DBs without password
    if not dbpass:
    # Connect without password
        dbcon = psycopg2.connect("host="+dbhost+" user="+dbuser+" dbname="+dbname+" port="+dbport)
    else:
        dbcon = psycopg2.connect("host="+dbhost+" user="+dbuser+" password="+dbpass+" dbname="+dbname+" port="+dbport)
    curs = dbcon.cursor()
    curs2 = dbcon.cursor()
    logging.debug("Pulling API vCode and Characters for keyID %i" % message)
    curs2.execute("""select "ID", "keyID", vcode, charid, corp from "killAPI" where "ID" = %s and active = True""", (message,))
    for result in curs2:
        sqlid = result[0]
        key = result[1]
        vcode = result[2]
        charid = result[3]
        corp = result[4]
        if corp:
            curs.execute("""update "killAPI" set updtime = now() + interval '1 hour 15 minutes' where "ID" = %s""", (sqlid,))
        else:
            curs.execute("""update "killAPI" set updtime = now() + interval '2 hours' where "ID" = %s""", (sqlid,))
        dbcon.commit()
        logging.debug("Found character information.  KeyID: %s  charID: %s Corp: %s" % (key, charid, corp))
        api = eveapi.EVEAPIConnection()
        auth = api.auth(keyID=key, vCode=vcode)
        if corp:
            try:
                killAPI = auth.corp.KillLog(characterID=charid)
            except eveapi.Error, e:
                logging.info("Corp API Key %s for character %s had an issue during API access %s" % (key, charid, e.code))
                if 200 <= e.code <= 209:
                    logging.info("Corp API Key %s for character %s is disabled due to Authentication issues" % (key, charid))
                    curs.execute("""update "killAPI" set active = False where "ID" = %s""", (sqlid,))
                continue
        else:
            try:
                killAPI = auth.char.KillLog(characterID=charid)
            except eveapi.Error, e:
                logging.info("Char API Key %s for character %s had an issue during API access %s" % (key, charid, e.code))
                if 200 <= e.code <= 205:
                    logging.info("Char API Key %s for character %s is disabled due to Authentication issues" % (key, charid))
                    curs.execute("""update "killAPI" set active = False where "ID" = %s""", (sqlid,))
                continue
        try:
            for kill in killAPI.kills:
                killid = kill.killID
                curs.execute("""select "killID" from "killList" where "killID" = %s""", (killid,))
                try:
                    if curs.fetchone() != None:
                        continue
                except ProgrammingError:
                    pass

                for items in kill.items:
                    curs.execute("""insert into "killItems" values(%s, %s, %s, %s, %s, %s)""", (killid, items.typeID,
                        items.flag, items.qtyDropped, items.qtyDestroyed, items.singleton))

                curs.execute("""insert into "killList" values (%s, %s, TIMESTAMPTZ 'epoch' + %s * '1 second'::interval, %s
                    )""", (killid, kill.solarSystemID, kill.killTime, kill.victim.characterID))
                curs.execute("""insert into "killVictim" values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", (killid,
                    kill.victim.allianceID, kill.victim.allianceName, kill.victim.characterID, kill.victim.characterName,
                    kill.victim.corporationID, kill.victim.corporationName, kill.victim.damageTaken, kill.victim.factionID,
                    kill.victim.factionName, kill.victim.shipTypeID))
                for attackers in kill.attackers:
                    curs.execute("""insert into "killAttackers" values(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::boolean, %s, %s)
                        """, (killid, attackers.characterID, attackers.characterName, attackers.corporationID,
                        attackers.corporationName, attackers.allianceID, attackers.allianceName,
                        attackers.factionID, attackers.factionName, attackers.securityStatus, attackers.damageDone,
                        attackers.finalBlow, attackers.weaponTypeID, attackers.shipTypeID))
                dbcon.commit()
        except Exception, err:
            print err
            return

if __name__ == '__main__':
    main()
