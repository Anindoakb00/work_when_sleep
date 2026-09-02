import pathlib
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


chrome_options = Options()
project_directory = pathlib.Path(__file__).resolve().parents[1]
chrome_options.add_argument("--start-maximized")
chrome_options.add_argument(f"--user-data-dir={project_directory / 'userdata'}")
chrome_options.add_argument('--profile-directory=Profile 8')
prefs = {"profile.default_content_setting_values.notifications": 2}
chrome_options.add_experimental_option("prefs", prefs)
chrome_options.add_argument('disable-infobars')
chrome_options.add_experimental_option("useAutomationExtension", False)
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])


class BaseBot:
    def __init__(self):
        self.driver = webdriver.Chrome(options=chrome_options)
