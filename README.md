There are a variety of good stories out there on the Internet, and oftentimes you'd like to download them and put them into an ebook format. However, if the author does not provide an ebook of his own, then it is a hassle to either manually download and combine each page or else write a script just for a single website. fetchstory.py is an attempt to improve this situation. It handles the dirty details of downloading the story: you just have to write a simple JSON *story file* for each story that you want to fetch. If you are familiar with CSS selectors, then this will generally take only 5-10 minutes to complete.

fetchstory.py produces ebooks in the EPUB format, though EPUB ebooks can easily be converted into many different formats. For example, to convert into a .mobi file compatible with Amazon Kindle devices, you could use ebook-convert (part of the Calibre project) or Amazon's kindlegen.

To run this script, you need Python 2.x and the Python modules `requests` and `lxml`. Then run `python2 fetchstory.py STORY_FILE.json`, and it will output the epub to a file in the same directory as the story file but with a .epub extension. For example, `python2 fetchstory.py stories/dungeon_keeper_ami.json` will use one of the included story files to download Dungeon Keeper Ami, putting the result in stories/dungeon_keeper_ami.epub.
    
A number of sample story files are provided in the `stories` directory. I recommend using one of them as a template when you try writing your own. **Be warned**: Although these are story files that I used successfully  at one point in time, I make *no* attempt at keeping them up-to-date. Because the chapter hierarchy (volumes, books, etc.) must be expressed in the story files, using an out-of-date story file will often result in recent chapters being miscategorized under the last section explicitly listed in the story file. Additionally, while the CSS selectors used by fetchstory.py tend to be *reasonably* stable (moreso than regex matches, for example), large changes to the story websites can completely break the story file.

**Story file format**

Each story file contains a JSON object with the following properties.

* name: The name of the book.
* author: The book's author.
* style: Extra CSS to add to the book. (optional)
* lang: A two-letter language code, to be inserted into the ebook's metadata. (optional, en default)
* wait_time: The number of seconds to wait between each pageload (optional, default 1)
* steps: A list of steps to follow when fetching the book.

Each step object has the following properties. For most properties, omitting the property uses the most recent value for that property in a previous step, so steps other than the first can often be quite short.

* method: `url` to fetch a URL. `next` to click the "next" link on the most-recently-downloaded page. `toc` to download and store a table of contents. `toc_next` to download the next link in the most-recently-downloaded table of contents. `next_url` to generate the next URL from the previous URL.
* url: The URL to process. For the `url` method, this can be an array of URLs to fetch in sequence.
* title: CSS selector for the title. If not provided or not found, a default of "chapter NNN" will be used, replacing NNN with the chapter number.
* body: CSS selector for the text of the chapter. If it is not found, then generally it will go onto the next step.
* remove: A list of CSS selectors that should be removed from the body. Note that the elements are removed in order, not all at once, which can affect the accuracy of some selectors.
* section: A string or list of strings specifying that this step is underneath the provided sub-section(s). This is used when constructing the ebook's table of contents.
* up: A number of sub-sections to end before starting the step.
* prev-next (`next` only): CSS selector for the next link. The first selected <a> which has a link that we have not already seen is chosen. So, if convenient, you can usually select both the previous and next links. If no unvisited links are selected, the step ends.
* last: After the step processes this URL, it will go onto the next step.
* toc (toc only): A CSS selector which will match all links in the table of contents
* ignore (toc only): A list of regular expressions. If any of them match a link that was matched by the CSS selector, then the link will not be downloaded.
* multiple: If 0 or omitted, only the first item matching the `body` selector will be considered. If 1, each match of the `body` selector will be considered a separate chapter.
* continue_on_endless: If 0 or omitted, the script will return an error if it ever attempts to download the same URL twice. If 1, this event will only end the step. This is useful when your CSS selectors will result in revisiting a page once you reach the end of a story/section.
* url_gen (next_url only): tcl code that must `return` the next URL to download. At the start of the tcl script, the `URL` variable will be set to the previous URL.

fetchstory.py makes some attempt to clean up source HTML so that it produces a valid EPUB file, but it can often still produce invalid EPUBs when dealing with real-world messy HTML. If the output is so screwed up that your ebook reader will not read it, try using the `remove` rule to remove whatever is causing the trouble.
