import OAuth2Util
import praw
import psycopg2
import re
import json
import requests
import urllib.parse
import urllib.request
import os
import sys
from bs4 import BeautifulSoup

try:
	user = 'TweakInfoBot'
	version = 'v66'
	userAgent = 'OS X 10.11 - com.tsunderedev.tweakinfo - ' + version + ' - detects tweaks mentioned in /r/jailbreak and /r/iOSthemes (by /u/hizinfiz) '
	subreddit = 'jailbreak'
	subreddit2 = 'iOSthemes'
	admin = 'hizinfiz'
except Exception as e:
	print (Exception, str(e))

replied = False

footer = '\n---\n\n^(*beep boop I\'m a bot*)\n\n^(Type the name of a tweak enclosed in double brackets `[[tweak name]]` and I\'ll look it up for you.)\n\n^[[Info](http://www.reddit.com/r/hizinfiz/wiki/TweakInfoBot)] ^[[Source](https://github.com/hizinfiz/TweakInfoBot)] ^[[Mistake?](http://www.reddit.com/message/compose/?to=' + admin + '&amp;subject=%2Fu%2FTweakInfoBot%20feedback;message=If%20you%20are%20providing%20feedback%20about%20a%20specific%20post%2C%20please%20include%20the%20link%20to%20that%20post.%20Thanks!)]'

urllib.parse.uses_netloc.append("postgres")
url = urllib.parse.urlparse(os.environ["DATABASE_URL"])

db = psycopg2.connect(
	database=url.path[1:],
	user=url.username,
	password=url.password,
	host=url.hostname,
	port=url.port
)
c = db.cursor()
c.execute('CREATE TABLE IF NOT EXISTS comments (SUB TEXT, LAST TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS posts (SUB TEXT, LAST TEXT)')
db.commit()
db.close()

# pattern = r'\[\[(\w\s)+\]\]'
# pattern = r'\[\[([\S\s][^\[\]]*)+\]\]'
# pattern = r'\[\[[\w\s`~!@#$%^&*()-_=+{}\\|;:'",<.>/?]+\]\]'
pattern = r'\[\[[\w\s`~\!\@\#\$\%\^\&\*\(\)\-\_\=\+\{\}\\\|\;\:\'\"\,\<\.\>\/\?]+\]\]'
spPattern = r'\[\[\s[\w`~\!\@\#\$\%\^\&\*\(\)\-\_\=\+\{\}\\\|\;\:\'\"\,\<\.\>\/\?]+\s\]\]'

# Check new comments from subreddit for tweak queries
def checkComments(sub):
	print ('    Checking comments from /r/' + sub + '...')
	s = r.get_subreddit(sub)
	count = 0

	# records the first comment checked to use as a stopping point in the next run
	for com in s.get_comments(limit = 1):
		first = com.id

	# get the most recent comments posted to the subreddit
	for com in s.get_comments(limit = 250):
		comID = com.id
		comBody = com.body
		comAut = com.author

		print('      Comment from ' + str(comAut))

		# ignored comments I posted
		if str(comAut) == 'TweakInfoBot':
			print('        I\'ll skip myself :P')
		else:
			# check if the current comment is stored in the database
			c.execute('SELECT * FROM comments WHERE LAST = %s', (comID,))

			# If the comment is not in the database, check for tweak requests
			if c.fetchone() == None:
				search = re.search(pattern, comBody, re.I|re.M)

				# This is a requested addition... [[...]] matches but [[ ... ]] does not
				if search:
					search != re.search(spPattern, comBody, re.I|re.M)

				# Leave a comment if there was a request
				if search:
					message = ''
					# this iterates through all of the matches since there might be multiple within a single comment
					for match in re.finditer(pattern, comBody, re.I|re.M):
						tweak = match.group()[2:-2]
						tweak = getTweak(tweak)
						message += tweak

					# check if the comment has replies from TweakInfoBot...
					# This method is necessary because in the event that the comment stored from the previous run gets removed 
					# by a mod, TweakInfoBot will recheck ALL of the comments, and in many cases TweakInfoBot will leave a
					# double or even triple reply. This coincidence surprisingly happened very often.
					cs = r.get_submission(com.permalink).comments[0]
					if cs.replies == []: # if there are no replies
						sendReply(message) # then leave a message
					else:
						for rep in cs.replies: # if there are replies, iterate through them
							if str(rep.author) == "TweakInfoBot": # and one of them is from TweakInfoBot
								replied = True # take note of that and don't reply
								print('        Already checked...')
						# if there are replies but TweakInfoBot has not yet replied, send a reply
						if replied == False:
							sendReply(message)			
			# If a comment was already left, break out of replying to comments since they were checked the last run through
			else:
				print('        Already checked...')
				break

		replied = False

	# Update with the first checked comment for the next run through
	# c.execute('INSERT INTO comments VALUES (%s, %s)', [sub, first])
	c.execute('UPDATE comments SET LAST = %s WHERE SUB = %s', [first, sub])
	db.commit()

# Check new posts from subreddit for tweak queries
def checkPosts(sub):
	print ('    Checking posts from /r/' + sub + '...')
	s = r.get_subreddit(sub)
	count = 0

	for pos in s.get_new(limit = 1):
		first = pos.id

	for pos in s.get_new(limit = 50):
		postID = pos.id
		postBody = pos.selftext
		postAut = pos.author

		print('      Post from ' + str(postAut))

		c.execute('SELECT * FROM posts WHERE LAST = %s', (postID,))

		# If a post was not yet left, check for tweak requests
		if c.fetchone() == None:
			search = re.search(pattern, postBody, re.I|re.M)

			if search:
				search != re.search(spPattern, comBody, re.I|re.M)

			# Leave a post if there was a request
			if search:
				message = ''
				for match in re.finditer(pattern, postBody, re.I|re.M):
					tweak = match.group()[2:-2]
					tweak = getTweak(tweak)
					message += tweak

				for com in pos.comments:
					if str(com.author) == 'TweakInfoBot':
						if com.is_root == True:
							print('        Already checked...')
						else:
							sendReply(message)				
		# If a post was already left, break out of replying to posts since they were checked the last run through
		else:
			print('        Already checked...')
			break

	# Update with the first checked post for the next run through
	# c.execute('INSERT INTO posts VALUES (%s, %s)', [sub, first])
	c.execute('UPDATE posts SET LAST = %s WHERE SUB = %s', [first, sub])
	db.commit()

# Send a reply, moved this into its own method because it showed up several times
def sendReply(message):
	try:
		com.reply(message + footer)
	except Exception as e:
		print (Exception, str(e))

# Tries to find information about a tweak
def getTweak(tweak):
	print ('        Getting info for ' + tweak)
	tweakNoSpace = tweak.replace(' ', '')
	msg = '* **' + tweak + '** - Could not find info about this tweak/theme\n'
	base = 'https://cydia.saurik.com/api/macciti?query='
	query = [base+tweak, base+tweakNoSpace]

	for q in query:
		r = requests.get(q)
		j = r.json()
		d = json.dumps(j)
		d = json.loads(d)

		for twk in d['results']:
			name = twk['display']

			# if there is an exact match
			if tweak == name: 
				msg = genMessage(twk)
				return msg
			# if the match is not exact
			else:
				name = removeTrailing(name).strip().lower()
				nameNoSpace = name.replace(' ', '').lower()

				if (name == tweak.lower()) | (name == tweakNoSpace.lower()) | (nameNoSpace == tweak.lower()) | (nameNoSpace == tweakNoSpace.lower()):
					msg = genMessage(twk)
					return msg

	return msg

# Get the price of a tweak
def getPrice(package):
	print ('          Getting price for ' + package)
	base = 'http://cydia.saurik.com/api/ibbignerd?query='
	query = base+package

	r = requests.get(query)
	j = r.json()

	if j == None:
		return 'Free'
	else:
		d = json.dumps(j)
		d = json.loads(d)

		price = '$' + str(d['msrp'])

		return price

# Get the repo of a tweak
def getRepo(link):
	html = urllib.request.urlopen(link)
	soup = BeautifulSoup (html, "html.parser")

	# All of the default repos have this CSS class towards the bottom of their depiction
	repo = soup.find('span', {'class' : 'source-name'}).contents[0]

	if repo == 'ModMyi.com': repo = 'ModMyi'

	return repo

# Generate the tweak info message (reddit formatted)
def genMessage(twk):
	print('        Found it!')
	link = 'http://cydia.saurik.com/package/' + str(twk['name'])
	rep = getRepo(link)
	typ = str(twk['section'])
	cos = getPrice(twk['name'])
	des = str(twk['summary'])

	msg = '* [**' + tweak + '**](' + link + ') -' + rep + ', ' + cos +  ' | ' + typ + ' | ' + des + '\n'

	return msg

# Some packages are named "Tweak [iOS ...]" or similar, this removes all the excess
def removeTrailing(name):
	separator = ['(','[','-','for']

	for sep in separator:
		head, div, tail = name.partition(sep)

		if div is not '':
			return head

	return head

if __name__ == '__main__':
	if not userAgent:
		print('Missing User Agent')
	else:
		print('Logging in...')
		r = praw.Reddit(userAgent + version)
		o = OAuth2Util.OAuth2Util(r)
		o.refresh(force=True)
		print('Logged in!')

		# sub = r.get_subreddit(subreddit)

	print('Connecting to database...')
	db = psycopg2.connect(
	database=url.path[1:],
	user=url.username,
	password=url.password,
	host=url.hostname,
	port=url.port
	)
	c = db.cursor()
	print('Connected to database!')

	print('Start TweakInfoBot for /r/' + subreddit + ' and /r/' + subreddit2)

	if len(sys.argv) > 1:
		if sys.argv[1] == 'JBcom':
			print('  RUNNING JBCOM')
			checkPosts(subreddit)
			checkComments(subreddit)
		if sys.argv[1] == 'ITcom':
			print('  RUNNING ITCOM')
			checkPosts(subreddit2)
			checkComments(subreddit2)
		if sys.argv[1] == 'test':
			print('  RUNNING TEST')
			checkPosts('hizinfiz')
			checkComments('hizinfiz')
		if sys.argv[1] == 'inbox':
			print('  RUNNING INBOX')
			pass

	print('End TweakInfoBot for /r/' + subreddit + ' and /r/' + subreddit2)

	db.close()