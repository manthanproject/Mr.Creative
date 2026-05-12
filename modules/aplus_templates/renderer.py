"""A+ Template Renderer — HTML/CSS templates → PNG via headless Chrome."""
import os, json, logging, time, uuid
logger = logging.getLogger('aplus')

def render_aplus_image(template_name, data, output_dir, width=970, height=600):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    html = _build_html(template_name, data, width, height)
    if not html:
        raise ValueError(f"Template '{template_name}' not found")

    temp_id = uuid.uuid4().hex[:8]
    temp_html = os.path.join(output_dir, f'_temp_aplus_{temp_id}.html')
    os.makedirs(output_dir, exist_ok=True)
    with open(temp_html, 'w', encoding='utf-8') as f:
        f.write(html)

    try:
        opts = Options()
        opts.add_argument('--headless=new')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-gpu')
        opts.add_argument(f'--window-size={width},{height}')
        opts.add_argument('--hide-scrollbars')
        opts.add_argument('--force-device-scale-factor=2')

        driver = None
        for dp in ['chromedriver.exe', 'chromedriver']:
            if os.path.exists(dp):
                driver = webdriver.Chrome(service=Service(executable_path=dp), options=opts)
                break
        if not driver:
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            except Exception:
                driver = webdriver.Chrome(options=opts)

        file_url = 'file:///' + os.path.abspath(temp_html).replace('\\', '/')
        driver.get(file_url)
        time.sleep(1)
        container = driver.find_element('id', 'aplus-container')
        actual_height = container.size['height']
        driver.set_window_size(width, actual_height + 50)
        time.sleep(0.3)

        output_filename = f'aplus_{template_name}_{temp_id}.png'
        output_path = os.path.join(output_dir, output_filename)
        container.screenshot(output_path)
        driver.quit()
        logger.info(f"[A+] Rendered {template_name} -> {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"[A+] Render error: {e}")
        raise
    finally:
        try: os.remove(temp_html)
        except OSError: pass

def _build_html(template_name, data, width, height):
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    template_path = os.path.join(templates_dir, f'{template_name}.html')
    if not os.path.exists(template_path):
        return None
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    data_json = json.dumps(data, ensure_ascii=False)
    html = html.replace('{{WIDTH}}', str(width))
    html = html.replace('{{HEIGHT}}', str(height))
    html = html.replace('{{DATA_JSON}}', data_json)
    for key, value in data.items():
        if isinstance(value, str):
            html = html.replace('{{' + key.upper() + '}}', value)
    return html

def get_available_templates():
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    templates = []
    if os.path.exists(templates_dir):
        for f in os.listdir(templates_dir):
            if f.endswith('.html'):
                templates.append({'name': f.replace('.html',''), 'label': f.replace('.html','').replace('_',' ').title()})
    return templates
