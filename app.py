import streamlit as st
import os
from dotenv import load_dotenv
import google.generativeai as genai
import requests
import json

# Charger les variables d'environnement
load_dotenv()

# URL ngrok ou Elasticsearch local
ngrok_url = 'https://6936-102-180-19-51.ngrok-free.app'

# Configuration du modèle Gemini Flash 1.5
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
gen_config = {
    "temperature": 0.5,
    "max_output_tokens": 512
}

gemini_model = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    generation_config=gen_config
)

# Fonction pour indexer une nouvelle question et réponse dans Elasticsearch
def index_question_in_elasticsearch(question, response, ngrok_url):
    doc = {
        'question': question,
        'response': response
    }
    
    # Imprimer le document avant de l'envoyer à Elasticsearch
    print("Document à indexer :", json.dumps(doc, indent=4))
    
    response = requests.post(f'{ngrok_url}/questions_reponses/_doc/', 
                             headers={"Content-Type": "application/json"}, 
                             data=json.dumps(doc))
    
    if response.status_code != 201:
        print(f"Erreur d'indexation pour la question : {response.status_code} - {response.text}")
    else:
        print("Question et réponse indexées avec succès.")

# Fonction pour générer une réponse unique en fonction de plusieurs articles
def generate_response_single(question, articles):
    context = "\n\n".join([f"Article {i+1}: {article['text']}" for i, article in enumerate(articles)])
    prompt = f"""Contexte : {context}\nQuestion : {question}\nGénère une réponse pertinente en fonction du contexte ci-dessus et de la question posée en citant tous les articles utilisés dans la réponse."""
    response = gemini_model.generate_content(prompt)
    return response.text

# Fonction pour générer une réponse lorsque la question est classée dans "general_embeddings"
def generate_response_general(question):
    prompt = f"""Question : {question}\nGénère une réponse pertinente à cette question. Notez que cette réponse est générée par un modèle automatique et il est conseillé de la vérifier."""
    response = gemini_model.generate_content(prompt)
    return response.text

# Fonction pour exécuter une recherche textuelle complète dans Elasticsearch pour les articles
def search_full_text(ngrok_url, index_name, query_text):
    search_query = {
        "query": {
            "match": {
                "text": query_text  # Rechercher les articles correspondant à ce texte
            }
        }
    }

    response = requests.post(f'{ngrok_url}/{index_name}/_search',
                             headers={"Content-Type": "application/json"},
                             data=json.dumps(search_query))
    
    if response.status_code == 200:
        results = response.json()
        return results['hits']['hits']
    else:
        st.error(f"Erreur lors de la recherche : {response.text}")
        return None

# Définir la fonction de classification de question selon les institutions
def classify_question(query_text):
    droits_humains_keywords = ["handicap", "indigence", "droits humains", "protection des personnes handicapées", "inclusion sociale", "personnes vulnérables"]
    police_judiciaire_keywords = ["violence", "crimes", "délits", "prévention de la violence", "justice pénale", "enquête judiciaire", "procédure pénale"]
    police_nationale_keywords = ["académie de police", "formation policière", "forces de l'ordre", "admission stagiaires", "missions de police", "sécurité publique"]
    securite_keywords = ["gardiennage", "sociétés privées de sécurité", "sécurité nationale", "sécurité privée", "protection des biens", "responsabilité professionnelle"]

    if any(keyword in query_text.lower() for keyword in droits_humains_keywords):
        return "droits_humains_embeddings"
    elif any(keyword in query_text.lower() for keyword in police_judiciaire_keywords):
        return "police_judiciaire_embeddings"
    elif any(keyword in query_text.lower() for keyword in police_nationale_keywords):
        return "police_nationale_embeddings"
    elif any(keyword in query_text.lower() for keyword in securite_keywords):
        return "securite_embeddings"
    else:
        return "general_embeddings"

# Fonction pour vérifier les questions/réponses stockées dans Elasticsearch
def get_all_questions_responses(ngrok_url):
    search_query = {
        "query": {
            "match_all": {}
        }
    }

    response = requests.post(f'{ngrok_url}/questions_reponses/_search', 
                             headers={"Content-Type": "application/json"}, 
                             data=json.dumps(search_query))

    if response.status_code == 200:
        results = response.json()
        if results['hits']['total']['value'] > 0:
            return results['hits']['hits']
        else:
            return "Aucun document trouvé dans Elasticsearch."
    else:
        return f"Erreur lors de la recherche : {response.text}"

# Interface principale Streamlit
def main():
    st.set_page_config(page_title="Générateur de réponses juridiques", page_icon="⚖️", layout="wide")
    
    st.markdown("<h1 style='text-align: center; font-size: 2.8em;'>⚖️ Générateur de réponses juridiques</h1>", unsafe_allow_html=True)

    st.markdown(
        "<p style='text-align: center; font-size: 1.2em;'>Bienvenue dans l'outil de génération de réponses juridiques. Posez vos questions et recevez des réponses basées sur des articles juridiques pertinents.</p>",
        unsafe_allow_html=True
    )

    # Ajout d'un bouton pour vérifier les questions/réponses stockées dans la barre latérale
    if st.sidebar.button("Vérifier les questions/réponses stockées"):
        st.sidebar.subheader("Questions et réponses stockées dans Elasticsearch")
        stored_data = get_all_questions_responses(ngrok_url)
        
        if isinstance(stored_data, str):
            st.sidebar.write(stored_data)
        else:
            for doc in stored_data:
                st.sidebar.write(f"Question : {doc['_source']['question']}")
                st.sidebar.write(f"Réponse : {doc['_source']['response']}")
                st.sidebar.write("---")

    query = st.text_input(label="", placeholder="Entrez votre question ici...", label_visibility="collapsed")

    if st.button("Envoyer la question", key="send_button"):
        if query:
            with st.spinner('Classification de la question...'):
                category = classify_question(query)

            if category == "general_embeddings":
                with st.spinner('Génération de la réponse...'):
                    response = generate_response_general(query)
                    st.subheader("Réponse générée :")
                    st.markdown(f"<strong>{response}</strong>", unsafe_allow_html=True)
                    st.info("Cette réponse a été générée par un modèle automatique. Veuillez vérifier les informations.")
                    index_question_in_elasticsearch(query, response, ngrok_url)
            else:
                with st.spinner('Recherche des articles pertinents...'):
                    articles = search_full_text(ngrok_url, category, query)

                if articles:
                    st.subheader("Articles trouvés :")
                    for i, article in enumerate(articles):
                        with st.expander(f"Article {i+1}"):
                            st.write(article['_source']['text'])

                    with st.spinner('Génération de la réponse...'):
                        response = generate_response_single(query, [article['_source'] for article in articles])
                        st.subheader("Réponse générée :")
                        st.markdown(f"<strong>{response}</strong>", unsafe_allow_html=True)
                        index_question_in_elasticsearch(query, response, ngrok_url)
                else:
                    st.error("Aucun article trouvé.")
        else:
            st.error("Veuillez entrer une question avant de soumettre.")

if __name__ == "__main__":
    main()
