# 📘 DOCUMENTATION TECHNIQUE COMPLÈTE - QANOUNI-AI (NIBRASSE)
**Version : 3.0 (OpenRouter Integration & Gemini 3)**
**Date : 21 Janvier 2026**
**Auteur : SALAH GASMI**

---

## 📑 TABLE DES MATIÈRES

1.  [VUE D'ENSEMBLE DU PROJET](#1-vue-densemble-du-projet)
2.  [ARCHITECTURE TECHNIQUE](#2-architecture-technique)
3.  [STRUCTURE DU PROJET](#3-structure-du-projet)
4.  [BASE DE DONNÉES (SUPABASE)](#4-base-de-données-supabase)
    *   [4.1. Modèle de Données (Schema)](#41-modèle-de-données-schema)
    *   [4.2. Indexation & Performance](#42-indexation--performance)
    *   [4.3. Fonctions RPC (Remote Procedure Calls)](#43-fonctions-rpc-remote-procedure-calls)
5.  [MOTEUR RAG & RECHERCHE (#servicesragpy)](#5-moteur-rag--recherche)
    *   [5.1. Pipeline d'Ingestion (Smart Chunking)](#51-pipeline-dingestion-smart-chunking)
    *   [5.2. Stratégie de Recherche Hybride (RRF)](#52-stratégie-de-recherche-hybride-rrf)
    *   [5.3. Reranking (Ré-ordonnancement)](#53-reranking-ré-ordonnancement)
6.  [LES 4 MODES FONCTIONNELS](#6-les-4-modes-fonctionnels)
    *   [Mode 1 : Moteur de Recherche Juridique](#mode-1--moteur-de-recherche-juridique)
    *   [Mode 2 : Consultant Juridique (Expert)](#mode-2--consultant-juridique-expert)
    *   [Mode 3 : Avocat / Plaidoirie](#mode-3--avocat--plaidoirie)
    *   [Mode 4 : Recherche de Jurisprudence](#mode-4--recherche-de-jurisprudence)
7.  [API BACKEND (FASTAPI)](#7-api-backend-fastapi)
8.  [FRONTEND (VANILLA JS)](#8-frontend-vanilla-js)
9.  [DÉPLOIEMENT & INSTALLATION](#9-déploiement--installation)

---

## 1. VUE D'ENSEMBLE DU PROJET

**QANOUNI-AI** est une plateforme d'intelligence juridique algérienne avancée. Contrairement aux simples chatbots, il s'agit d'un système **RAG (Retrieval-Augmented Generation)** spécialisé qui combine :
1.  **Recherche Sémantique (Vectorielle)** : Pour comprendre le sens ("vol avec violence").
2.  **Recherche Lexicale (BM25)** : Pour trouver les termes exacts et numéros d'articles ("Article 350").
3.  **LLM (Génération)** : Pour synthétiser des réponses juridiques, rédiger des plaidoiries ou conseiller.

L'objectif est de fournir aux professionnels du droit (avocats, juristes) et aux citoyens un outil fiable, sourcé et précis, basé exclusivement sur le Droit Algérien.

---

## 2. ARCHITECTURE TECHNIQUE

Le système repose sur une architecture moderne **Client-Serveur** découplée :

*   **Backend (Python / FastAPI)** :
    *   Gère la logique métier, l'IA, et les connexions BDD.
    *   Utilise `FastAPI` pour des performances élevées (Asynchrone).
    *   **Architecture 100% OpenRouter (Unified Logic)** :
        *   **Gemini 3 Flash Preview** : Pour le "Cerveau Lourd" (Consultations, Plaidoiries, Jurisprudence). Context window: 1M tokens.
        *   **Gemini 2.0 Flash** : Pour le "Cerveau Rapide" (Extraction, Reranking, Recherche Générale). Optimisé pour le coût/vitesse.
*   **Base de Données (Supabase / PostgreSQL)** :
    *   Stocke les documents, les vecteurs (pgvector), et les utilisateurs.
    *   Gère la recherche vectorielle via RPC.
*   **Frontend (HTML5 / Vanilla JS / CSS3)** :
    *   Interface légère, rapide, sans framework lourd (React/Vue).
    *   Comporte un visualiseur de documents PDF/Texte intégré.
    *   Responsive (Mobile & Desktop).

---

## 3. STRUCTURE DU PROJET

Le projet a été nettoyé et séparé en deux dossiers distincts pour une clarté maximale :

```
QUANOUNI_CLEAN/
├── backend/                   # LE CERVEAU (API Python)
│   ├── app/
│   │   ├── api/               # Routes API (Endpoints)
│   │   │   ├── routes.py      # Routes Générales (Auth, Upload, Chat)
│   │   │   └── legal.py       # Routes Spécialisées (Jurisprudence, Plaidoirie)
│   │   ├── core/              # Configuration (config.py)
│   │   ├── services/          # Logique Métier
│   │   │   ├── rag.py         # Moteur RAG (Le cœur du système)
│   │   │   ├── vector_store.py# Connecteur Supabase Vector
│   │   │   ├── embedding.py   # Génération d'Embeddings (Gemini)
│   │   │   └── bm25_service.py # Recherche par Mots-clés
│   │   └── main.py            # Point d'entrée FastAPI
│   ├── .env                   # Variables d'Environnement (Clés API) - inclut OPENROUTER_KEY
│   ├── Dockerfile             # Pour déploiement conteneurisé
│   └── requirements.txt       # Dépendances Python
│
└── frontend/                  # LE VISAGE (Interface Web)
    ├── index.html             # Page Principale (Dashboard)
    ├── login.html             # Page d'Authentification
    ├── app.js                 # Logique JS (DOM Manipulation + Fetch API)
    ├── style.css              # Styles (Thème sombre/clair, Animations)
    └── assets/                # Logos, Icônes
```

---

## 4. BASE DE DONNÉES (SUPABASE)

Nous utilisons **PostgreSQL** avec l'extension `pgvector`. Le schéma est optimisé pour le "Smart Chunking" (découpage intelligent des textes juridiques).

### 4.1. Modèle de Données (Schema)

#### Table `documents` (Les livres)
Stocke les métadonnées globales du fichier source.

| Colonne | Type | Description |
| :--- | :--- | :--- |
| `id` | BIGSERIAL | Clé Primaire |
| `filename` | TEXT | Nom du fichier (ex: `Code_Penal.txt`) |
| `category` | TEXT | 'law' (Loi) ou 'jurisprudence_full' (Arrêt) |
| `jurisdiction`| TEXT | 'mahkmama_olya' (Cour Suprême) ou NULL |
| `law_name` | TEXT | Nom canonique (ex: "Code Pénal") |
| `metadata` | JSONB | Métadonnées flexibles supplémentaires |

#### Table `chunk` (Les paragraphes/articles)
C'est ici que réside l'intelligence. Chaque article ou principe est stocké individuellement.

| Colonne | Type | Description |
| :--- | :--- | :--- |
| `id` | BIGSERIAL | Clé Primaire |
| `document_id` | FK | Lien vers le document parent |
| `chunk_index` | INT | Ordre dans le document |
| `content` | TEXT | Le texte juridiques (L'article lui-même) |
| `embedding` | VECTOR(768)| Représentation mathématique (Gemini Embedding) |
| `chunk_type` | TEXT | **CRUCIAL**: 'article', 'principle' (Mabda2), 'reasoning' (Haythiat) |
| `article_number`| TEXT | Numéro extrait (ex: "350") pour recherche exacte |

### 4.2. Indexation & Performance
*   **HNSW Index (`chunk_embedding_idx`)** : Permet une recherche vectorielle ultra-rapide (Millisecondes) même sur des millions de chunks.
*   **B-Tree Indexes** : Sur `article_number`, `chunk_type`, et `law_name` pour des filtres SQL instantanés.

### 4.3. Fonctions RPC (Remote Procedure Calls)
La fonction `match_documents` est le moteur de recherche côté base de données.
Elle prend un vecteur de requête + des filtres, et retourne les chunks les plus proches sémantiquement.

```sql
FUNCTION match_documents(
    query_embedding VECTOR(768), 
    filter_category TEXT, 
    ...
)
```

---

## 5. MOTEUR RAG & RECHERCHE

Le fichier `backend/app/services/rag.py` contient l'algorithme de cerveau du système.

### 5.1. Pipeline d'Ingestion (Smart Chunking)
Lorsqu'un fichier est uploadé, il n'est pas coupé bêtement tous les 500 mots.
*   **Pour les Lois** : Il détecte " المادة X" et coupe exactement aux frontières des articles.
*   **Pour la Jurisprudence** : Il sépare "Le Principe" (Mabda2) des "Motifs" (Haythiat).

### 5.2. Stratégie de Recherche Hybride (RRF)
Le moteur n'utilise pas uniquement les vecteurs, car l'arabe juridique est complexe. Il utilise **RRF (Reciprocal Rank Fusion)** :
1.  **Recherche Vectorielle (30%)** : Trouve le sens.
2.  **Recherche BM25 (70%)** : Trouve les mots exacts (ex: "Article 40").
*   **Résultat** : Une précision redoutable.

### 5.3. Reranking (Ré-ordonnancement)
Les résultats bruts sont analysés par **Gemini 2.0 Flash (via OpenRouter)** qui agit comme un juge :
*"Cette loi parle de vol, mais l'utilisateur a demandé vol D'ÉLECTRICITÉ. Je déclasse cet article général"* -> Cela assure que le top 3 est toujours pertinent.

---

## 6. LES 4 MODES FONCTIONNELS

### Mode 1 : Moteur de Recherche Juridique 🔍
*   **Technique** : Hybrid Search + Reranking (Gemini 2) + Génération de réponse (Gemini 2).
*   **Optimisation** : Vitesse maximale pour les questions/réponses rapides.

### Mode 2 : Consultant Juridique (Expert) ⚖️
*   **Technique** : **Gemini 3 Flash Preview**.
*   **Optimisation** : Utilise une fenêtre de contexte de **1 Million Tokens** pour lire les textes intégraux des lois (jusqu'à 50,000 caractères par source) sans hallucination.

### Mode 3 : Avocat / Plaidoirie 📜
*   **Technique** : **Gemini 3 Flash Preview**.
*   **Optimisation** : Génère des documents complexes de 28,000+ caractères avec une éloquence juridique supérieure (Syllogisme, Terminologie).

### Mode 4 : Recherche de Jurisprudence 🏛️
*   **Technique** : Stratégie "Broad Fetch & Local Filter".
    *   Récupère 200 documents divers.
    *   Filtre localement pour ne garder que les arrêts de la Cour Suprême.
    *   Reranking intelligent des 20 meilleurs arrêts par Gemini 3.
*   **Résultat** : Découverte d'arrêts rares ("Needle in a haystack").

---

## 7. API BACKEND (FASTAPI)

| Méthode | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/login` | Authentification (JWT Token) |
| `POST` | `/api/query` | Recherche principale (Mode 1 & 2) |
| `POST` | `/api/legal-consultant` | Mode Consultant Dédié |
| `POST` | `/api/legal/pleading` | Génération de Plaidoirie |
| `POST` | `/api/cases` | Gestion des dossiers clients (CRUD) |
| `POST` | `/api/upload` | Upload et Ingestion de fichiers |

---

## 8. FRONTEND (VANILLA JS)

L'interface est conçue pour être "State-of-the-Art" sans la complexité de React.
*   **`app.js`** : Gère tout (Navigation SPA, Appels API, Rendu Markdown).
*   **Composants Clés** :
    *   `displayConsultation()` : Affiche la réponse structurée avec les puces sources interactives.
    *   `handleFiles()` : Gère le Drag & Drop.
    *   `openDocumentViewer()` : Ouvre une modale pour lire le PDF/TXT original.

## 9. DÉPLOIEMENT & INSTALLATION

### Prérequis
*   Python 3.10+
*   Compte Supabase (URL + Key)
*   Compte OpenRouter (Clé API).

### Installation Rapide
1.  **Copier** le dossier `QUANOUNI_CLEAN`.
2.  **Backend** :
    ```bash
    cd backend
    pip install -r requirements.txt
    uvicorn app.main:app --reload
    ```
3.  **Frontend** : Ouvrir `frontend/index.html`.

---
**Fin du Document**

---

## 10. RECENT UPDATES (v3.0) - 21 Jan 2026

### 10.1. Migration Complète vers OpenRouter 🔄
*   **Objectif** : Unifier la facturation et accéder aux modèles "SOTA" (State-of-the-Art) sans quotas limitatifs.
*   **Solution** : Implémentation d'un client `generate_openrouter` universel dans `rag.py`.
*   **Stratégie à deux niveaux (Tiered Strategy)** :
    *   **Niveau Lourd (Heavy)** : `google/gemini-3-flash-preview` pour les tâches cognitives complexes (Consultation, Plaidoirie).
    *   **Niveau Léger (Light)** : `google/gemini-2.0-flash-001` pour les tâches à haut volume (Recherche, Extraction, Reranking).

### 10.2. Maximisation du Contexte (Context Window)
*   **Problème** : L'ancien système tronquait les documents à 4000 caractères, perdant des détails cruciaux.
*   **Solution** : Avec Gemini 3 (1M Context), nous avons supprimé cette limite. Le système lit désormais jusqu'à **50,000 caractères** par document, garantissant une précision absolue.

### 10.3. Correction de la Recherche de Jurisprudence
*   **Problème** : Les filtres RPC de Supabase limitaient trop les résultats.
*   **Solution** : Adoption d'une approche "Fetch 200 -> Filter Python -> Rerank". Cela permet de trouver des aiguilles dans une botte de foin.

### 10.4. Audit Log Fix
*   Patch du service d'audit pour gérer les "legacy_id" et éviter les erreurs UUID dans PostgreSQL.
