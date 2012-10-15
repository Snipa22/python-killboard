import ConfigParser
import psycopg2
from hotqueue import HotQueue

config = ConfigParser.ConfigParser()
config.read(['api.conf', 'local_api.conf'])
dbhost = config.get('Database', 'dbhost')
dbname = config.get('Database', 'dbname')
dbuser = config.get('Database', 'dbuser')
dbpass = config.get('Database', 'dbpass')
dbport = config.get('Database', 'dbport')
redisdb = config.get('Redis', 'redishost')

queue = HotQueue("killboard-API", host=redisdb, port=6379, db=0)

if not dbpass:
# Connect without password
    dbcon = psycopg2.connect("host="+dbhost+" user="+dbuser+" dbname="+dbname+" port="+dbport)
else:
    dbcon = psycopg2.connect("host="+dbhost+" user="+dbuser+" password="+dbpass+" dbname="+dbname+" port="+dbport)

curs = dbcon.cursor()
curs2 = dbcon.cursor()
curs.execute("""select * from "killAPI" where updtime <= now()""")
for api in curs:
    sqlid = result[0]
    curs2.execute("""update "killAPI" set updtime = (now() + interval '15 minutes') where "ID" = %s""", (sqlid,))
    queue.put(sqlid)