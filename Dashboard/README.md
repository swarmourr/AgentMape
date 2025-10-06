# 🎯 MAPE-K Real-Time Dashboard

Dashboard web simple pour monitorer le système MAPE-K (Monitor, Analyzer, Planner, Executor) en temps réel.

## ✨ Fonctionnalités

- 📊 **Monitoring en temps réel** des 3 agents (Monitor, Analyzer, Planner)
- 🔄 **Auto-refresh toutes les 3 secondes**
- 📈 **Statistiques des workflows** (Running, Failed, Held, Success)
- 📋 **Liste des workflows récents**
- 🎨 **Interface style terminal** avec couleurs et animations
- ⚡ **Léger et rapide** (pas de frameworks lourds)

## 🚀 Installation

```bash
cd /Users/hamzasafri/Desktop/AgentMape/Dashboard

# Installer les dépendances
pip3 install -r requirements.txt
```

## 📖 Utilisation

### 1. Démarrer les agents (dans l'ordre)

```bash
# Terminal 1 : Monitor
cd /Users/hamzasafri/Desktop/AgentMape/Monitoring
python3 server_rest.py

# Terminal 2 : Analyzer
cd /Users/hamzasafri/Desktop/AgentMape/Analyzer
python3 analyzer_rest.py

# Terminal 3 : Planner
cd /Users/hamzasafri/Desktop/AgentMape/Planner
python3 planner_rest.py
```

### 2. Démarrer le Dashboard

```bash
# Terminal 4 : Dashboard
cd /Users/hamzasafri/Desktop/AgentMape/Dashboard
python3 dashboard_server.py
```

### 3. Ouvrir dans le navigateur

```
http://localhost:8085
```

## 🎨 Interface

Le dashboard affiche :

### Agents Status
- ✅ **Monitor** - État de santé, temps de réponse
- ✅ **Analyzer** - État de santé, nombre d'analyses complétées
- ✅ **Planner** - État de santé, nombre de plans générés

### Workflow Statistics
- 🔵 **Running** - Workflows en cours d'exécution
- 🔴 **Failed** - Workflows échoués (en attente d'analyse)
- 🟡 **Held** - Workflows en attente
- 🟢 **Success** - Workflows complétés avec succès

### Recent Workflows
- Liste des 10 derniers workflows détectés
- Statut de chaque workflow
- Timestamp de détection

## ⚙️ Configuration

Modifier les URLs des agents dans `dashboard_server.py` :

```python
MONITOR_URL = "http://localhost:8080"
ANALYZER_URL = "http://localhost:8081"
PLANNER_URL = "http://localhost:8082"
DASHBOARD_PORT = 8085
```

## 🔌 API Endpoints

Le dashboard expose également des APIs REST :

### `GET /api/data`
Retourne toutes les données (agents + workflows + stats)

```bash
curl http://localhost:8085/api/data
```

### `GET /api/agents`
Retourne uniquement le status des agents

```bash
curl http://localhost:8085/api/agents
```

### `GET /api/workflows`
Retourne les workflows et leurs counts

```bash
curl http://localhost:8085/api/workflows
```

## 🐛 Troubleshooting

### Le dashboard affiche "Unhealthy" pour un agent

1. Vérifier que l'agent est démarré
2. Vérifier que le port est correct
3. Tester l'API de health :
   ```bash
   curl http://localhost:8080/health  # Monitor
   curl http://localhost:8081/health  # Analyzer
   curl http://localhost:8082/health  # Planner
   ```

### Aucun workflow n'apparaît

- Le Monitor doit être configuré pour surveiller un répertoire Pegasus
- Lancer un workflow Pegasus pour voir l'activité

### Erreur "Connection refused"

- Vérifier que tous les agents sont démarrés
- Vérifier les ports dans la configuration

## 📊 Captures d'écran

Le dashboard utilise :
- **Box drawing characters** pour un look moderne
- **Gradient backgrounds** pour l'esthétique
- **Animations** pour les éléments dynamiques
- **Colors** pour différencier les statuts
- **Auto-refresh** toutes les 3 secondes

## 🔮 Améliorations Futures

- [ ] WebSocket pour updates instantanées
- [ ] Graphiques de métriques (Chart.js)
- [ ] Historique des workflows
- [ ] Filtrage et recherche
- [ ] Notifications desktop
- [ ] Export des données (CSV, JSON)
- [ ] Dark/Light theme toggle

## 📝 Notes

- Le dashboard est **stateless** (pas de base de données)
- Toutes les données viennent des agents en temps réel
- Auto-refresh toutes les 3 secondes (configurable dans le HTML)
- Léger et rapide (~50 lignes de Python + ~250 lignes HTML/CSS/JS)
