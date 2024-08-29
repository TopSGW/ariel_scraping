import os
import time
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


class ProductScraper:
    def __init__(self, url):
        self.url = url
        self.products_data = []
        self.pagetype = ''

    def fetch_content(self):
        """Fetch the page content using Selenium to handle dynamic content."""
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')  # Run in headless mode
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            driver.get(self.url)
            time.sleep(5)  # Wait for dynamic content to load

            page_source = driver.page_source
            driver.quit()
            return page_source
        except Exception as e:
            print(f"Error fetching page content: {e}")
            return None

    def parse_listing_page(self, soup):
        """Parse the product listing page to extract product names and URLs."""
        product_list_holder = soup.find('div', id='productListHolder')
        if not product_list_holder:
            return []

        products = []

        for product in product_list_holder.find_all(
            'div', class_='col-12 col-sm-6 col-lg-3 text-center pb-4 pr-2 mx-0 mb-4'
        ):
            product_name = self.extract_text(product.find('a', class_='link-item mb-0 font-weight-bold'))
            product_description = self.extract_text(product.find('p', class_='link-item mb-0'))
            sku = self.extract_sku(product)
            price = self.extract_text(product.find('strong', class_='currency'))

            products.append({
                'Product Name': product_name,
                'Product Description': product_description,
                'SKU': sku,
                'Price': price,
            })
        return products

    def extract_text(self, tag):
        """Helper method to safely extract text from a BeautifulSoup tag."""
        return tag.get_text(strip=True) if tag else 'N/A'

    def extract_sku(self, product):
        """Extract SKU from product."""
        sku_tag = product.find_all('p', class_='link-item mb-0')[1] if len(
            product.find_all('p', class_='link-item mb-0')) > 1 else None
        return self.extract_text(sku_tag)

    def parse_detail_page(self, soup):
        """Parse the product detail page to extract the required details."""
        product_detail = soup.find('div', id='productDetail')
        if not product_detail:
            return {}

        data = {
            'SKU': self.extract_sku_detail(product_detail),
            'Item Size': self.extract_item_size(product_detail),
            'Imprint Areas': self.extract_imprint_areas(soup),
            'Pricing': self.extract_pricing(product_detail)
        }
        return data

    def extract_sku_detail(self, product_detail):
        """Extract SKU from product detail page."""
        sku_tag = product_detail.find('p', class_='mx-0 px-0 mt-1 mb-4')
        if sku_tag and "Item ID:" in sku_tag.get_text():
            return sku_tag.get_text(strip=True).split('Item ID:')[-1].strip()
        return 'N/A'

    def extract_item_size(self, product_detail):
        """Extract item size from product detail page."""
        size_tag = product_detail.find('h5', string='Size:')
        return size_tag.find_next_sibling(string=True).strip() if size_tag else 'N/A'

    def extract_imprint_areas(self, soup):
        """Extract imprint areas and methods from product detail page."""
        imprint_areas = []
        imprint_areas_section = soup.find('div', id='printMethods')
        if not imprint_areas_section:
            return imprint_areas

        heading_ids = imprint_areas_section.find_all(
            lambda tag: tag.name == 'div' and re.match(r'heading\d+', tag.get('id', ''))
        )

        for heading in heading_ids:
            button = heading.find('button')
            method_name = self.extract_text(button)
            method_details = {'Method': method_name, 'Locations': []}
            collapse_id = button.get('data-target', '') if button else None
            if collapse_id:
                method_details['Locations'] = self.extract_locations(imprint_areas_section, collapse_id)
            imprint_areas.append(method_details)
        return imprint_areas

    def extract_locations(self, imprint_areas_section, collapse_id):
        """Extract location and size details from the imprint areas."""
        locations = []
        collapse_section = imprint_areas_section.find('div', id=collapse_id.strip('#'))
        if not collapse_section:
            return locations

        location_tables = collapse_section.find_all('table')
        if len(location_tables) < 3:
            return locations

        third_table = location_tables[2]
        headers = [header.get_text(strip=True).lower() for header in third_table.find_all('th')]
        if 'location' not in headers or 'size' not in headers:
            return locations

        location_index = headers.index('location')
        size_index = headers.index('size')

        for row in third_table.find_all('tr')[1:]:
            columns = row.find_all('td')
            if len(columns) > max(location_index, size_index):
                location_name = self.extract_text(columns[location_index])
                size_text = self.extract_text(columns[size_index])
                width, height = self.extract_size(size_text)
                if width and height:
                    locations.append({'Location': location_name, 'Width': width, 'Height': height})
        return locations

    def extract_size(self, size_text):
        """Extract width and height from size string."""
        size_match = re.search(r'(\d+(\.\d+)?)\s*[\"\'“”]?\s*[Xx]\s*(\d+(\.\d+)?)\s*[\"\'“”]?', size_text)
        return (size_match.group(1), size_match.group(3)) if size_match else (None, None)

    def extract_pricing(self, product_detail):
        """Extract pricing details from product detail page."""
        pricing = {'Quantities': [], 'Prices': []}
        pricing_table = product_detail.find('table', class_='pricetable')
        if not pricing_table:
            return pricing

        quantity_headers = pricing_table.find('thead').find_all('th')[1:]  # Skip the first header ('Quantity')
        pricing['Quantities'] = [header.get_text(strip=True).replace('&nbsp;', '') for header in quantity_headers]

        price_row = pricing_table.find('tbody').find('tr')
        price_cells = price_row.find_all('th')[1:]  # Skip the first cell ('Price (5C)')
        pricing['Prices'] = [price_cell.get_text(strip=True).replace('&nbsp;', '') for price_cell in price_cells]

        return pricing

    def save_to_csv(self, data):
        """Save the extracted data to a CSV file."""
        file_exists = os.path.isfile('scraped_products.csv')
        df = pd.DataFrame(data)
        df.to_csv('scraped_products.csv', mode='a', header=not file_exists, index=False)
        print('Data saved to scraped_products.csv')

    def display_data(self, data):
        """Print the extracted data to the console."""
        if self.pagetype == 'list':
            for product in data:
                print("Product Listing Details:")
                print(f"Product Name: {product.get('Product Name', 'N/A')}")
                print(f"Product Description: {product.get('Product Description', 'N/A')}")
                print(f"SKU: {product.get('SKU', 'N/A')}")
                print(f"Price: {product.get('Price', 'N/A')}")
                print("-" * 40)
        else:
            for product in data:
                print(f"SKU: {product.get('SKU', 'N/A')}")
                print(f"Item Size: {product.get('Item Size', 'N/A')}")
                print("Imprint Areas:")
                for area in product.get('Imprint Areas', []):
                    print(f"  Method: {area['Method']}")
                    for location in area['Locations']:
                        print(f"    Location: {location['Location']}, Width: {location['Width']} inches, Height: {location['Height']} inches")
                print("Pricing:")
                for quantity, price in zip(product['Pricing']['Quantities'], product['Pricing']['Prices']):
                    print(f"  {quantity}: {price}")
                print("-" * 40)

    def scrape(self):
        html_content = self.fetch_content()
        if not html_content:
            print("Failed to fetch content.")
            return

        soup = BeautifulSoup(html_content, 'html.parser')

        if soup.find('div', id='productListHolder'):
            print("Scraping a product listing page...")
            products = self.parse_listing_page(soup)
            self.products_data.extend(products)
            self.pagetype = 'list'
        else:
            print("Scraping a product detail page...")
            product_data = self.parse_detail_page(soup)
            self.products_data.append(product_data)
            self.pagetype = 'detail'

        self.display_data(self.products_data)
        self.save_to_csv(self.products_data)


if __name__ == "__main__":
    url = input("Enter the product URL: ")
    scraper = ProductScraper(url)
    scraper.scrape()
