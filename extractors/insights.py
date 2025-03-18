import os
import yaml
import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
from datetime import datetime

# Load configuration from a YAML file
def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../config/settings.yaml")
    print(f"Loading config from: {config_path}")
    
    with open(config_path, "r") as file:
        return yaml.safe_load(file)

CONFIG = load_config()

# Initialize WebDriver
def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    return driver

# Function to extract insights from a page
def extract_insights(driver, url, date_range, xpaths):
    insights_data = []
    
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpaths["insights_cards"])))
    articles = driver.find_elements(By.XPATH, xpaths["insights_cards"])
    
    for article in articles:
        try:
            insight_name = article.find_element(By.XPATH, xpaths["insight_name"]).text.strip() + " (insight)"
        except:
            insight_name = "N/A"
        
        try:
            value_element = article.find_element(By.XPATH, ".//span[contains(@id, 'percent_') or contains(@id, 'articles_')] | " + xpaths["value"])
            value = value_element.text.strip() if value_element.text.strip() else "N/A"
        except:
            value = "N/A"
        
        collection_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Human-readable timestamp
        page_url = driver.current_url  # Capture current page URL
        
        insights_data.append({
            "date_range": date_range,
            "Insight": insight_name,
            "Value": value,
            "Page_URL": page_url,
            "collection_time": collection_time
        })
    
    return insights_data

# Main function to process all URLs
def scrape_insights(environment):
    driver = get_driver()
    all_insights = []
    xpaths = CONFIG["xpaths"]
    urls = CONFIG["urls"][environment]
    
    for url in urls:
        print(f"Scraping: {url}")
        driver.get(url)
        time.sleep(CONFIG["delays"]["page_load"])
        
        year_buttons = driver.find_elements(By.XPATH, xpaths["year_buttons"])
        
        if len(year_buttons) >= 2:
            # Extract insights for each date range
            for i, button in enumerate(year_buttons[:2]):
                button.click()
                time.sleep(CONFIG["delays"]["data_load"])
                date_range = button.text.strip()
                all_insights.extend(extract_insights(driver, url, date_range, xpaths))
            
            try:
                all_time_button = driver.find_element(By.XPATH, xpaths["all_time_button"])
                all_time_button.click()
                time.sleep(CONFIG["delays"]["data_load"])
                date_range = all_time_button.text.strip()
                all_insights.extend(extract_insights(driver, url, date_range, xpaths))
            except:
                print("No all-time button found.")
        else:
            print("No year buttons found, extracting without date_range")
            all_insights.extend(extract_insights(driver, url, "", xpaths))
            
    driver.quit()
    return all_insights

# Run the scraper and export to CSV
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["staging", "dev"], required=True, help="Specify environment: staging or dev")
    args = parser.parse_args()
    
    insights_data = scrape_insights(args.env)
    output_file = f"insights_{args.env}_data.csv"
    df = pd.DataFrame(insights_data)
    df.to_csv(output_file, index=False)
    print(f"Data saved to {output_file}")

if __name__ == "__main__":
    main()