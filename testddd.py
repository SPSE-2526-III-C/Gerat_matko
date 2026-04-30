from flask import Flask, render_template_string, request
import requests

app = Flask(__name__)

# HTML Šablóna (všetko v jednom súbore pre rýchle spustenie)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Open Food Facts Vyhľadávač</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
        .product { border: 1px solid #ddd; padding: 10px; margin-bottom: 10px; border-radius: 5px; display: flex; align-items: center; }
        img { max-width: 100px; margin-right: 20px; }
        input { padding: 10px; width: 300px; }
        button { padding: 10px; background: #28a745; color: white; border: none; cursor: pointer; }
    </style>
</head>
<body>
    <h1>Vyhľadaj potraviny 🍎</h1>
    <form method="GET">
        <input type="text" name="q" placeholder="Napr. Nutella alebo Horalky" value="{{ query }}">
        <button type="submit">Hľadať</button>
    </form>

    <hr>

    {% if products %}
        <h2>Výsledky pre: "{{ query }}"</h2>
        {% for p in products %}
            <div class="product">
                {% if p.image_url %}
                    <img src="{{ p.image_url }}" alt="produkt">
                {% endif %}
                <div>
                    <strong>{{ p.product_name or 'Neznámy názov' }}</strong><br>
                    Značka: {{ p.brands or 'Neznáma' }}<br>
                    Nutri-skóre: {{ p.nutrition_grades_tags[0] if p.nutrition_grades_tags else 'N/A' | upper }}
                </div>
            </div>
        {% endfor %}
    {% elif query %}
        <p>Nenašli sa žiadne produkty.</p>
    {% endif %}
</body>
</html>
"""

@app.route('/')
def index():
    query = request.args.get('q', '')
    products = []
    
    if query:
        # Open Food Facts API URL pre vyhľadávanie
        # 'user_agent' je dôležitý, aby vás API neblokovalo
        url = f"https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": 10
        }
        headers = {
            "User-Agent": "MojaFlaskApp/1.0 (kontakt: tvoj@email.com)"
        }
        
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            products = response.json().get('products', [])

    return render_template_string(HTML_TEMPLATE, products=products, query=query)

if __name__ == '__main__':
    app.run(debug=True)