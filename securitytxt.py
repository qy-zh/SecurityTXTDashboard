import requests
import os
import csv
import logging
import favicon
import socket
import requests
import urllib3
from urllib.parse import urlparse
from urllib.request import urlopen
from urllib.error import URLError
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# keep silent! see https://urllib3.readthedocs.io/en/latest/advanced-usage.html#tls-warnings for details
urllib3.disable_warnings()

logging.basicConfig(
    filename='error.log', 
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')

# Extract information from the response after calling the url
# primarily to extract site title from url for txt-files as input
def extract_information_from_url(url):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.title.string if soup.title else None
    except requests.RequestException as e:
        logging.error(f"Error extracting information from {url}: {e}")
        return None

# Extract information (title + url) from csv file
def csv_to_results(input_file):
    with open(input_file, 'r', newline='', encoding='utf-8') as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=';')
        # Skip the header
        header = next(csv_reader)  
        results = {}

        for row in csv_reader:
            if len(row) >= 2:
                # Remove leading/trailing whitespaces
                url = row[1].strip()
                # checking if url in file is welformed, if domain is registered and scheme is https or http
                if is_valid_url(url) and is_existing_domain(url) and https_or_http(url):
                    title = row[0].strip()
                    results[url] = {'Title': title, 'BASEURL': url}
                else:
                    logging.error(f"Something else ist wrong with (csv source): {url}")
        #print ("results after csv read\n", results)
        return results

# Extract information (url) from txt file
def txt_to_results(file_path):
    results = {}
    with open(file_path, 'r') as file:
        for line in file:
            url = line.strip()
            # checking if url in file is welformed, if domain is registered and scheme is https or http
            if is_valid_url(url) and is_existing_domain(url) and https_or_http(url):
                title = extract_information_from_url(url)
                results[url] = {'Title': title, 'BASEURL': url}
            else:
                logging.error(f"Somehow else invalid URL {url} in {file_path}")
    return results

# Check whether the url is valid or not
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        logging.error(f"Malformed URL?: {url} - {e}")
        return False

# check, if domain is registered or not
def is_existing_domain(url):
    hostname = urlparse(url).netloc
    try:
        h = socket.gethostbyname(hostname)
        return True
    except socket.gaierror:
        # DNS lookup failed, hostname cannot be resolved
        logging.error(f"Domain not existing: {hostname} - please correct input")
        return False


#check if given URL is reachable, if not try other scheme and only throw error, if both schemes fail
def https_or_http(url):
    hostname = urlparse(url).netloc
    http_scheme = "http://"
    http_url = http_scheme + hostname
    try:
        # verify is an annoying option, keeps complaining, see beginning of file urllib3.disable_warnings() silences it
        response = requests.get(url, timeout=6, allow_redirects=True, verify=False)
        parsed_response = urlparse(response.url)
        return all([parsed_response.scheme, parsed_response.netloc])
    except:
        try:
            response_http = requests.get(http_url, timeout=12, allow_redirects=False)
            parsed_response_http = urlparse(response_http.url)
            logging.info(f"No https: {http_url}")
            return (http_url)
        except ValueError:
            logging.error(f"Something went wrong - no http, no https: {hostname} - {e}")
            return False

# Check whether the page is sucessfully loaded or not
def check_page_not_found(url):
    try:
        response = requests.get(url)
        # Raise an exception for HTTP errors (4xx and 5xx status codes)
        response.raise_for_status()  
        
        # Check if the text "page not found" or "seite nicht gefunden" is present in the response content
        # this is because CMS don't deliver http status codes but redirect to pages - maybe TODO NTH maybe more legant solution possible?
        page_not_found_texts = ["page not found", "seite nicht gefunden"]
        for text in page_not_found_texts:
            if text.lower() in response.text.lower():
                # Text "Page not found" is present
                return False  
            if "contact" not in response.text.lower():
                return False

        # Page is accessible
        return True  

    except requests.RequestException as e:
        return False

# Extract the text information from the security.txt of the website if it exits
def check_security_txt(url):
    # define the path where to check for security.txt
    paths_to_check = [".well-known/security.txt", "security.txt"]

    for path in paths_to_check:
        try:
            response = requests.get(url + path, allow_redirects=False)
            # Print(url + path, response.status_code)
            # TODO why here to check for "page not found"?
            if response.status_code == 200 and check_page_not_found(url + path):
                return response.text
        except requests.RequestException as e:
            logging.error(f"Error checking {path} for {url}: {e}")

    return None

# Generate html file for the security.txt results
def generate_html_report(results, filename, output_file, template_file="templates/page_template.html"):
    with open(template_file, 'r') as template:
        template_content = template.read()

    with open(output_file, 'w') as file:
        file.write(template_content.replace('{report_title}', generate_report_title(filename))
                                   .replace('{report_content}', generate_card_content(results)))

# Generate title for each report       
def generate_report_title(filename):
    return f"<h1 style='text-align: center; font-family: Arial, sans-serif;'>Security.txt Dashboard for {filename}</h1>"


# Generate the result of each url in a card
def generate_card_content(results):
    card_content = '<div class="grid" data-masonry=\'{ "itemSelector": ".grid-item" }\'>'
    # TODO this results contain the URL and the status of the Security.txt, no title!
    # print ("results before card generation", results)
    for url, result in results.items():
        favicon_url = get_favicon_url(url)
        alert_class = "alert-success" if result.get('SecurityTxt') is not None else "alert-warning"

        if url.endswith('.txt'):
            # For .txt files, use the URL as the card title
            card_title = f"<h5 class='card-title'><a href='{url}' target='_blank' rel='noopener'>{url}</a></h5>"
            print ("set card in txt file")
        elif url.endswith('.csv'):
            # For .csv files, use the title from the CSV as the card title
            card_title = f"<h5 class='card-title'>{result.get('Title', 'Unknown')}</h5>"
            print ("set card in csv file")
        else:
            # Use the URL as the default card title
            #card_title = f"<h5 class='card-title'><a href='{url}' target='_blank' rel='noopener'>{url}</a></h5>"
            card_title = f"<h5 class='card-title'><a href='{url}' target='_blank' rel='noopener'>{result.get('Title', 'Unknown')}</a></h5>"
            #print ("set card in some file")

        card_content += f"""
            <div class="grid-item alert {alert_class}" role="alert">
                <div class="card text-center">
                    <div class="d-flex align-items-center justify-content-center">
                        <img class="card-img-top" src="{favicon_url}" alt="Card image cap" width="32" height="32" style="max-width: 32px; max-height: 32px; margin-top: 5px; margin-bottom: 2px;">
                    </div>
                    <div class="card-body">
                        {card_title}
                        <ul class="list-group list-group-flush">
        """

        if 'SecurityTxt' in result and result['SecurityTxt'] is not None:
            card_content += f"<li class='list-group-item'><pre>{result['SecurityTxt']}</pre></li>"
        else:
            card_content += "<li class='list-group-item'>No security.txt found</li>"

        card_content += """
                        </ul>
                    </div>
                </div>
            </div>
        """

    card_content += '</div>'
    return card_content

# Get the favicon from the given url in size 32*32
def get_favicon_url(url):
    try:
        icons = favicon.get(url)
        if len(icons) == 0:
            return "globe2.jpg"
            print ("no favicon")
            logging.info(f"No favicon for {url}")
        else:
            return icons[0].url
    except requests.RequestException as e:
            logging.error(f"Error checking {url} for favicon: {e}")
            return "globe2.jpg"
    #domain = urlparse(url).hostname
    #return f"https://www.google.com/s2/favicons?domain={domain}&s=32"

# Generate an index from the existing html results
def generate_html_index():
    # Read the HTML template
    with open("templates/index_template.html", "r") as template_file:
        index_template = template_file.read()

    # Get a list of HTML files in the public directory
    html_files = [file for file in os.listdir("public/") if file.endswith(".html") and file != "index.html"]

    # Generate the list items for each HTML file
    list_items = ""
    for html_file in html_files:
        list_items += f"<li class=\"list-group-item\"><a href=\"{html_file}\">{html_file}</a></li>\n"

    # Insert the list items into the template
    final_index = index_template.format(list_items=list_items)

    # Write the final index to a new HTML file
    with open("public/index.html", "w") as index_file:
        index_file.write(final_index)

# Here is where the magic starts
def main(input_folder, output_folder):

    # loop through input folder and generate like-named output file
    for input_file in os.listdir(input_folder):
        input_file_path = os.path.join(input_folder, input_file)
        filename = os.path.splitext(input_file)[0]
        output_file_path = os.path.join(output_folder, f"{filename}_report.html")

        logging.info(f"{input_file} - processing")

        if input_file.lower().endswith('.txt'):
            output = txt_to_results(input_file_path)
        elif input_file.lower().endswith('.csv'):
            output = csv_to_results(input_file_path)
        else:
            logging.error(f"Unsupported file format: {input_file}")
            continue
        #print ("\033[1m 'output' after reading files\033[0m", output)

        # define new dictionary
        results = {}
        # outer_key is the url from the input file, BASEURL is the validated url in the inner dictionary
        for outer_key, inner_dict in output.items():
            baseurl = inner_dict['BASEURL']
            title = inner_dict['Title']
            # check the availability of the security.txt
            security_txt_result = check_security_txt(baseurl)
            # packing all elements into the results dictionary
            results[outer_key] = {
                'URL' : outer_key,
                'Title' : title,
                'SecurityTxt': security_txt_result
            }
        
        #print (results, "\n before generating html\n\033[1mBREAK\033[0m\n")
        generate_html_report(results, filename, output_file_path)
        generate_html_index()
        #print (input_file, " done\n")

if __name__ == "__main__":
    input_folder = "input" 
    output_folder = "public"
    main(input_folder, output_folder)
