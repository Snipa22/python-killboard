import ConfigParser
import psycopg2
from hotqueue import HotQueue
import gevent
from gevent.pool import Pool
from gevent import monkey; gevent.monkey.patch_all()
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

MAX_NUM_POOL_WORKERS = 75

queue = HotQueue("killboard-API", host=redisdb, port=6379, db=0)

logging.basicConfig(format='%(asctime)s:%(levelname)s:%(message)s', level=logging.DEBUG)

# use a greenlet pool to cap the number of workers at a reasonable level
greenlet_pool = Pool(size=MAX_NUM_POOL_WORKERS)

def main():
    for message in queue.consume():
        greenlet_pool.spawn(worker, message)

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
    curs2.execute("""select "keyID", vcode, charid, corp from "killAPI" where "keyID" = %s and active = True""", (message,))
    for result in curs2:
        key = result[0]
        vcode = result[1]
        charid = result[2]
        corp = result[3]
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
                continue
        else:
            try:
                killAPI = auth.char.KillLog(characterID=charid)
            except eveapi.Error, e:
                logging.info("Char API Key %s for character %s had an issue during API access %s" % (key, charid, e.code))
                if 200 <= e.code <= 205:
                    logging.info("Char API Key %s for character %s is disabled due to Authentication issues" % (key, charid))
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
                for items in kill.items:
                    curs.execute("""insert into "killItems" values(%s, %s, %s, %s, %s, %s)""", (killid, items.typeID,
                        items.flag, items.qtyDropped, items.qtyDestroyed, items.singleton))
                dbcon.commit()
        except Exception, err:
            print err
            return

if __name__ == '__main__':
    main()
