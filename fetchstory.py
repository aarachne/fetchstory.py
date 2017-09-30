from lxml import etree
from lxml.cssselect import CSSSelector
import requests
import sys, json, os, shutil, uuid, time, zipfile, re, tempfile, urlparse
import Tkinter, traceback, cgi
from threading import Timer
from copy import deepcopy

# needed for a timer later
def doNothing():
	pass
thread = None

# write a message, clearing anything that has already been written on this line
def msg(msg, newline = False):
	MSG_LIMIT = 70
		
	sys.stderr.write("\r" + msg[-MSG_LIMIT:] + " "*(MSG_LIMIT - len(msg)) + ("\n" if newline else ""))
	sys.stderr.flush()
	

ALLOWED_TAGS = ['a', 'abbr', 'address', 'b', 'bdi', 'bdo', 'blockquote', 'br', 'caption', 'cite', 'code', 'col', 'colgroup', 'dd', 'del', 'details', 'dfn', 'div', 'dl', 'dt', 'em', 'footer', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hr', 'i', 'ins', 'kbd', 'li', 'mark', 'nav', 'ol', 'output', 'p', 'pre', 'q', 'rp', 'rt', 'ruby', 's', 'samp', 'section', 'span', 'strong', 'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'textarea', 'tfoot', 'th', 'thead', 'time', 'tr', 'u', 'ul', 'var', 'wbr']
ALLOWED_ATTR = ['abbr', 'align', 'border', 'cite', 'class', 'cols', 'colspan', 'datetime', 'dir', 'disabled', 'download', 'for', 'headers', 'hidden', 'href', 'hreflang', 'id', 'lang', 'media', 'name', 'open', 'placeholder', 'readonly', 'rel', 'reversed', 'rows', 'rowspan', 'scope', 'scoped', 'sortable', 'sorted', 'start', 'style', 'tabindex', 'target', 'title', 'translate', 'type', 'value', 'wrap']
BAD_BLOCK = ['aside', 'article', 'dialog', 'dir', 'fieldset', 'figcaption', 'figure', 'form', 'legend', 'main', 'map', 'menu', 'meter', 'noframes', 'noscript']
BAD_INLINE = ['font', 'label', 'menu', 'menuitem', 'progress']
BAD_DEL = ['applet', 'audio', 'area', 'button', 'canvas', 'datalist', 'embed', 'frame', 'frameset', 'iframe', 'img', 'input', 'keygen', 'object', 'optgroup', 'option', 'param', 'script', 'select', 'source', 'style', 'track', 'video']

XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
XHTML = "{%s}" % XHTML_NAMESPACE
NSMAP = {None: XHTML_NAMESPACE}

RETRIES = 7

if len(sys.argv) <= 1:
	print 'Usage: python2 fetchstory.py story_file.json'
	print 'The ebook will be output in the same directory as the json file,'
	print 'but with a .epub extension'
	sys.exit(1)

# import scripts
scripts = []
for arg in range(1, len(sys.argv)):
	try:
		with open(sys.argv[arg], 'r') as file:
			try:
				scripts.append(json.load(file))
				scripts[len(scripts)-1]['filename'] = os.path.splitext(sys.argv[arg])[0] + '.epub'
			except ValueError as e:
				print 'Invalid JSON in ' + sys.argv[arg] + ' : ' + str(e)
				sys.exit(1)
	except IOError as e:
		print 'Unable to open file ' + sys.argv[arg] + ' : ' + str(e)

# go through all of the scripts
for script in scripts:
	try:
		tempdir = tempfile.mkdtemp()
		
		bookName = script['name'] if 'name' in script else 'Unnamed book'
		bookAuth = script['author'] if 'author' in script else 'Unknown'
		bookLang = script['lang'] if 'lang' in script else 'en'
		waitTime = 1.0*script['wait_time'] if 'wait_time' in script else 1.0
		extraStyle = script['style'] if 'style' in script else ''
		
		# setup structure
		mime = open(os.path.join(tempdir, "mimetype"), 'w')
		mime.write("application/epub+zip")
		mime.close()
		os.makedirs(os.path.join(tempdir, 'META-INF'))
		container = open(os.path.join(tempdir, "META-INF", "container.xml"), 'w')
		container.write("""<?xml version="1.0" encoding="UTF-8"?>
	<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
	   <rootfiles>
		  <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
	   </rootfiles>
	</container>""")
		container.close()
		os.makedirs(os.path.join(tempdir, 'EPUB'))
		os.makedirs(os.path.join(tempdir, 'EPUB', 'xhtml'))
		os.makedirs(os.path.join(tempdir, 'EPUB', 'css'))
		
		# write chapters
		title = None
		body = None
		remove = []
		prev = None
		toc = []
		tocNum = -1
		tocSel = None
		tocIgnore = []
		parser = etree.HTMLParser()
		stepNum = 0
		method = None
		prev_next = None
		allowMult = False
		continueOnEndless = False
		url_gen = None
		urlsNum = 0
		
		chapters = [] # lists of (type, name)
		TYPE_CHAPTER = 1
		TYPE_SECTION = 2
		TYPE_UP = 3
		
		numChapters = 0
		
		urls = set()
		url = None
		
		# go through the steps
		lastSteps = [-1, -2]
		while stepNum < len(script['steps']):
			multIndex = 0
			multLimit = 9999
			step = script['steps'][stepNum]
			lastSteps[1] = lastSteps[0]
			lastSteps[0] = stepNum
			
			# we went past the last
			if url is not None and 'last' in step and url == step['last']:
				stepNum += 1
				continue
			
			# import new settings
			if 'title' in step:
				title = step['title']
			if 'continue_on_endless' in step:
				continueOnEndless = step['continue_on_endless'] == 1
			if 'multiple' in step:
				allowMult = step['multiple'] == 1
			if 'body' in step:
				body = step['body']
			if 'remove' in step:
				remove = step['remove']
			if 'method' in step:
				method = step['method']
			if 'prev_next' in step:
				prev_next = step['prev_next']
			if 'toc' in step:
				tocSel = step['toc']
			if 'url_gen' in step:
				url_gen = step['url_gen']
			if 'ignore' in step:
				tocIgnore = step['ignore']
				for i in range(len(tocIgnore)):
					tocIgnore[i] = re.compile(tocIgnore[i], re.IGNORECASE)
					
			if 'up' in step and stepNum != lastSteps[1]:
				for i in range(step['up']):
					chapters.append((TYPE_UP, ''))
			if 'section' in step and stepNum != lastSteps[1]:
				if isinstance(step['section'], basestring):
					chapters.append((TYPE_SECTION, step['section']))
				else:
					for sec in step['section']:
						chapters.append((TYPE_SECTION, sec))
			if stepNum != lastSteps[1]:
				urlsNum = 0
			
			# get new URL, etc.
			if method == 'url':
				if isinstance(step['url'], basestring):
					url = step['url']
					stepNum += 1
				else:
					url = step['url'][urlsNum]
					urlsNum += 1
					if urlsNum == len(step['url']):
						urlsNum = 0
						stepNum += 1
			elif method == 'next':
				sel = CSSSelector(prev_next)
				url = sel(prev)
				found = False
				for s in url:
					if 'href' not in s.attrib:
						continue
					s = s.attrib['href']
					s = urlparse.urljoin(baseurl, s)
					# ignore URLs we've already seen
					if s not in urls:
						found = True
						url = s
						break
				if not found:
					stepNum += 1
					continue
				
			elif method == 'next_url':
				tclsh = Tkinter.Tcl()
				try:
					url = tclsh.eval('set URL {' + url + '}; ' + url_gen)
				except:
					raise Exception("Error when executing tcl script in step " + str(stepNum+1))
			elif method == 'toc':
				url = step['url']
				toc = []
				tocNum = -1
				stepNum += 1
			elif method == 'toc_next':
				tocNum += 1
				if tocNum >= len(toc):
					stepNum += 1
					continue
				url = toc[tocNum]
			else:
				raise Exception('No valid method given in step '+str(stepNum+1))
			urls.add(url)
			
			# limit the number of requests we perform
			if thread is not None:
				thread.join()
				
			# retry a few times
			retries = 0
			ok = False
			while not ok:
				try:
					req = requests.get(url)
					ok = True
				except ConnectionError:
					retries += 1
					if retries >= RETRIES:
						raise
					time.sleep(waitTime*(2**retries))
					
			
			#start the waitTime timer
			thread = Timer(waitTime, doNothing, ())
			thread.start()
			
			if 'content-type' in req.headers:
				parser = etree.HTMLParser(encoding=req.encoding)
			else:
				parser = etree.HTMLParser()
			
				
			tree = etree.fromstring(req.content, parser)
			
			baseurl = url
			baseTag = tree.find(".//base")
			if baseTag is not None:
				baseurl = baseTag.attrib['href']
			
			# do toc processing instead of normal processing
			if method == 'toc':
				sel = CSSSelector(tocSel)
				for link in sel(tree):
					if 'href' not in link.attrib:
						continue
					link = urlparse.urljoin(baseurl, link.attrib['href'])
					fail = False
					for ex in tocIgnore:
						if ex.search(link) is not None:
							fail = True
							break
					if not fail:
						toc.append(link)
				continue
			
			prev = deepcopy(tree)
			
			# get the body, maybe multiple times
			firstLoop = True
			sel = CSSSelector(body)
			sel = sel(tree)
			multLimit = len(sel)
			# reached the end (probably 404)
			if method == 'next_url' and multLimit == 0:
				stepNum += 1
				continue
			while (not allowMult and firstLoop) or (allowMult and multIndex < multLimit):
				firstLoop = False
				
				chapTitle = None
				if title is not None and title != '':
					sel = CSSSelector(title)
					chapTitle = sel(tree)
					if len(chapTitle) > multIndex:
						chapTitle = chapTitle[multIndex].text
				if chapTitle is None or not isinstance(chapTitle, basestring):
					chapTitle = 'Chapter ' + str(numChapters+1)
				
				sel = CSSSelector(body)
				sel = sel(tree)
				chapBody = sel[multIndex]
				multIndex += 1
				
				# remove specified items from body
				for item in remove:
					sel = CSSSelector(item)
					for toRemove in sel(chapBody):
						toRemove.getparent().remove(toRemove)
				
				# log chapters for later
				chapters.append((TYPE_CHAPTER, chapTitle))
				numChapters += 1
				msg(script['filename'] + " chapter " + str(numChapters) + " (step " + str(stepNum+1) + "/" + str(len(script['steps'])) + ")")
				
				# title page
				if numChapters == 1:
					newT = etree.Element(XHTML + "html", nsmap=NSMAP)
					headT = etree.SubElement(newT, XHTML + "head")
					(etree.SubElement(headT, XHTML + "title")).text = bookName
					etree.SubElement(headT, XHTML + "meta", attrib={'charset':'utf-8'})
					etree.SubElement(headT, XHTML + "link", attrib={'rel':'stylesheet', 'type':'text/css', 'href':'../css/main.css'})
					bodyT = etree.SubElement(newT, XHTML + "body", attrib={'id':'bookTitlePage'})
					(etree.SubElement(bodyT, XHTML + "h1")).text = bookName
					(etree.SubElement(bodyT, XHTML + 'p')).text = 'By ' + bookAuth
					p = etree.SubElement(bodyT, XHTML + 'p')
					p.text = 'Fetched from '
					note = etree.SubElement(p, XHTML + 'a', attrib={'href': url})
					note.text = url
					note.tail = ' using fetchstory.py. Note that by automatically fetching the story, you have avoided viewing its advertisements; please consider a small donation to the author if you enjoy the story.'
					
					out = open(os.path.join(tempdir, 'EPUB', 'xhtml', 'title.xhtml'), 'w')
					out.write(('<?xml version="1.0" encoding="utf-8"?>' + "\r\n" + etree.tostring(newT, pretty_print=True)).encode('utf-8'))
					out.close()
					
					out = open(os.path.join(tempdir, 'EPUB', 'css', 'main.css'), 'w')
					out.write("""body { font-family: Georgia, Baskerville, serif; font-size: 12pt; line-height:1.5; text-align: justify}
	h1,h2,h3,h4,h5,h6 {font-family: "Helvetica", "Arial", sans-serif; text-align:center}
	h1 {font-size:25pt}
	h2 { font-size:18pt}
	h3 { font-size:15pt}
	h4 { font-size:13pt}
	h5 { font-size:11pt}
	h6 { font-size:10pt}
	p {margin: 0; text-indent: 5mm}
	#bookTitlePage {text-align:center} """ +  extraStyle)
					out.close()
				
				# construct new document
				newX = etree.Element(XHTML + "html", nsmap=NSMAP)
				headX = etree.SubElement(newX, XHTML + "head")
				(etree.SubElement(headX, XHTML + "title")).text = chapTitle + ' - ' + bookName
				etree.SubElement(headX, XHTML + "meta", attrib={'charset':'utf-8'})
				etree.SubElement(headX, XHTML + "link", attrib={'rel':'stylesheet', 'type':'text/css', 'href':'../css/main.css'})
				bodyX = etree.SubElement(newX, XHTML + "body", attrib={'id':'ch{0:04d}Page'.format(numChapters)})

				chapTitleX = etree.SubElement(bodyX, XHTML + 'h2')
				chapTitleX.text = chapTitle
				
				# try to fixup the source HTML a bit when copying
				def copyDoc(src, dst):
					for child in src:
						attrib = {}
						tag = child.tag
						for a in child.attrib.keys():
							if a in ALLOWED_ATTR:
								attrib[a] = child.attrib[a]
						
						if tag == 'a' and 'name' in attrib and 'id' not in attrib:
							attrib['id'] = attrib['name']
							del attrib['id']
						
						if tag is etree.Comment:
							continue
						
						if tag not in ALLOWED_TAGS:
							if tag in BAD_INLINE:
								tag = 'span'
								attrib = {}
							elif tag in BAD_BLOCK:
								tag = 'div'
								attrib = {}
							elif tag in BAD_DEL:
								continue
							elif tag == 'acronym':
								tag = 'abbr'
							elif tag == 'tt':
								tag = 'kbd'
							elif tag == 'big':
								tag = 'span'
								attrib['style'] = 'font-size: larger;' + ('' if 'style' not in attrib else attrib['style'])
							elif tag == 'center':
								tag = 'div'
								attrib['style'] = 'text-align: center;' + ('' if 'style' not in attrib else attrib['style'])
							elif tag == 'small':
								tag = 'span'
								attrib['style'] = 'font-size: smaller;' + ('' if 'style' not in attrib else attrib['style'])
							else:
								tag = 'div'
								attrib = {}
								
						
						newEl = etree.SubElement(dst, XHTML + tag, attrib=attrib)
						newEl.tail = child.tail
						newEl.text = child.text
						copyDoc(child, newEl)

				chapTitleX.tail = chapBody.text
				copyDoc(chapBody, bodyX)
				
				out = open(os.path.join(tempdir, 'EPUB', 'xhtml', 'ch{0:04d}.xhtml'.format(numChapters)), 'w')
				out.write(('<?xml version="1.0" encoding="utf-8"?>' + "\r\n" + etree.tostring(newX, pretty_print=True)).encode('utf-8'))
				out.close()
		# chapters written, create manifests
		out = open(os.path.join(tempdir, 'EPUB', 'package.opf'), 'w')
		manifest = '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
   <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:identifier id="uid">''' + str(uuid.uuid1()) + '''</dc:identifier>
      <dc:title>''' + bookName + '''</dc:title>
      <dc:creator>''' + bookAuth + '''</dc:creator>
      <dc:language>''' + bookLang + '''</dc:language>
      <meta property="dcterms:modified">''' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + '''</meta>
   </metadata>
   <manifest>
      <item href="xhtml/title.xhtml" id="title" media-type="application/xhtml+xml"/>
      <item href="xhtml/nav.xhtml" id="nav" media-type="application/xhtml+xml" properties="nav"/>'''
		for c in range(1, numChapters+1):
			manifest += "\r\n      " + '<item href="xhtml/' + 'ch{0:04d}'.format(c) + '.xhtml" id="' + 'ch{0:04d}'.format(c) + '" media-type="application/xhtml+xml"/>'
		manifest += "\r\n      " + '<item href="css/main.css" media-type="text/css" id="css"/>'
		# (if there were any additional images, etc., we'd need to list them here)
		manifest += '''
   </manifest>
   <spine>
      <itemref idref="title"/>
      <itemref idref="nav" linear="no"/>'''
		for c in range(1, numChapters+1):
			manifest += "\r\n      " + '<itemref idref="' + 'ch{0:04d}'.format(c) + '"/>'
		manifest += '''
   </spine>
</package>'''
		
		out.write(manifest.encode('utf-8'))
		out.close()
		
		# table of contents
		out = open(os.path.join(tempdir, 'EPUB', 'xhtml', 'nav.xhtml'), 'w')
		
		manifest = '''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
	<head>
		<meta charset="utf-8" />
		<title>Table of Contents - ''' + bookName + '''</title>
		<link rel="stylesheet" type="text/css" href="../css/main.css" />
	</head>
	<body>
		<nav epub:type="toc" id="toc">
			<h1 class="title">Table of Contents</h1>

			<ol>
				<li id="title"><a href="title.xhtml">Title page</a></li>
				<li id="nav"><a href="nav.xhtml">Table of Contents</a></li>'''
				
		indent = 4
		chapNum = 0
		for chapter in chapters:
			if chapter[0] == TYPE_CHAPTER:
				chapNum += 1
				manifest += "\r\n" + (indent*"\t") + '<li id="' + 'ch{0:04d}'.format(chapNum) + '"><a href="' + 'ch{0:04d}'.format(chapNum) + '.xhtml">' + cgi.escape(chapter[1]) + '</a></li>'
			elif chapter[0] == TYPE_SECTION:
				manifest += "\r\n" + (indent*"\t") + '<li><span>' + cgi.escape(chapter[1]) + '</span><ol>'
				indent += 1
			elif chapter[0] == TYPE_UP:
				indent -= 1
				manifest += "\r\n" + (indent*"\t") + '</ol></li>'
			else:
				raise exception('Invalid type')
		for i in range(indent-4):
			manifest += "\r\n" + (indent*"\t") + '</ol></li>'
			
		manifest += '''
			</ol>
		</nav>
	</body>
</html>'''
		out.write(manifest.encode('utf-8'))
		out.close()
		
		# zip it to create final epub
		zip = zipfile.ZipFile(script['filename'], 'w', zipfile.ZIP_DEFLATED)
		def zipdir(path, zip):
			for root, dirs, files in os.walk(path):
				for file in files:
					zip.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), tempdir))
		zip.write(os.path.join(tempdir, 'mimetype'), 'mimetype')
		zipdir(os.path.join(tempdir, 'META-INF'), zip)
		zipdir(os.path.join(tempdir, 'EPUB'), zip)
		zip.close()
		msg(script['filename'] + ' done', True)
	except TypeError as e:
		msg(script['filename'] + ' ERROR (wrong type in json?):', True)
		traceback.print_exc()
		if script is not scripts[-1]:
			msg('Continuing...', True)
	except KeyError as e:
		msg(script['filename'] + ' ERROR (missing value in json?):', True)
		traceback.print_exc()
		if script is not scripts[-1]:
			msg('Continuing...', True)
	except Exception as e:
		msg(script['filename'] + ' ERROR:', True)
		traceback.print_exc()
		if script is not scripts[-1]:
			msg('Continuing...', True)
	finally:
		shutil.rmtree(tempdir, True)
	