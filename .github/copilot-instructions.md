# Instructions Copilot - AgentMape (FR)

But: Ce fichier vise à rendre un agent IA productif rapidement dans ce dépôt MAPE-K (Monitor→Analyzer→Planner→Executor).

## Rappel rapide (start / santé)
- Démarrage global: `./start_system.sh` (crée venv si nécessaire, lance Monitor, PegasusProvider, Analyzer, Planner, Executor, Dashboard). ✅
- Démarrage individuel (exemples):
  - Monitor: `cd Monitoring && python server_rest.py` (port 8080, endpoint `/health`)
  - Analyzer: `cd Analyzer && python analyzer_rest.py` (expose prompts et endpoints, par défaut 8081)
  - Planner: `cd Planner && python planner_rest.py` (port 8082)
  - Pegasus Provider: `cd PegasusProvider && python pegasus_provider_service.py` (port 8084)
  - Dashboard: `cd Dashboard && python dashboard_server.py` (port 5000)
- Logs: `tail -f logs/*.log` et PIDs enregistrés dans `logs/*.pid`.

## Architecture & flux de données (essentiel)
- Pattern MAPE-K: Monitor → Analyzer → Planner → (Executor optional) + Dashboard + PegasusProvider.
- Monitor: extrait stderr des `.out` jobs, mappe chemins temporaires `/srv/...` vers PFN réels et envoie metadata (workflow YAML path, submit_dir) au Analyzer.
- Analyzer: utilise prompts structurés (voir `Analyzer/analyzer_rest.py`) et **doit** retourner une réponse JSON structurée (champ `problems_and_solutions`, `confidence_score`, etc.).
- Planner: lit l'analyse + catalogues (transformation/replica/site) et génère un plan exécutable en JSON (commands, risk, validation, new-submission steps). Voir `Planner/planner_rest.py` pour règles détaillées.
- Executor: (par défaut non automatique) responsable d'appliquer les plans—actuellement souvent manuel.
- Persist: agents utilisent TinyDB (`planner_db.json`, etc.) pour stockage léger.

## Règles critiques / conventions spécifiques au projet
- NE JAMAIS modifier `braindump.yml` ni les fichiers générés dans `.pegasus/`. Ce sont des métadonnées d'exécution.
- Les scripts temporaires dans `/srv/./...` sont des artefacts d'exécution. Si une erreur de script nécessite une correction, modifier le script source (workflow generator) ou le fichier source réel — pas le fichier `/srv/...`.
- Analyzer: quand vous demandez des fichiers pour réparation, suivez la logique `files_needed_for_fix` (chemin absolu + raison). Par défaut, si la cause est ressource ou fichier manquant, utilisez `[]` (Planner a déjà le catalogue).
- Planner: TOUJOURS proposer une NOUVELLE soumission après modification du YAML (`pegasus-plan --dir <workflow.yml> --submit`). Ne pas utiliser `--cleanup inplace` pour failed/held runs.
- Pour corrections de réplica: privilégier `pegasus-rc-client insert --lfn ... --pfn file://... --site local` plutôt que d'éditer braindump.
- Tri des erreurs: stderr prime sur pegasus-analyzer (les logs pegasus montrent souvent des « cascade errors » — prioriser l'analyse de stderr).

## Exemples concrets à reproduire
- Analyzer → JSON attendu (extrait): `{"problems_and_solutions":[{"problem":"...","solution":"...","error_level":"transformation","file_path":"/abs/path","files_needed_for_fix":[{"path":"/abs/path","reason":"..."}]}],"confidence_score":{...}}`.
- Planner → stratégie: modifier catalogues (site/replica/transformation) ou générateur de workflow, fournir commandes shell exactes, indiquer `risk` et `rollback` + `pegasus-plan --dir ... --submit`.

## Intégrations et dépendances
- LLM local préféré: Ollama (configurable via `ollama_api_base`, `ollama_model` dans les managers `Analyzer` / `Planner`). Les appels sont souvent en streaming pour gérer de longues réponses.
- Outils Pegasus attendus: `pegasus-plan`, `pegasus-rc-client`, `pegasus-analyzer`, `pegasus-status`.
- Outils utilitaires: `yq` est utilisé pour modifier YAML embarqués.
- Endpoints REST/ports: Monitor 8080, Analyzer 8081, Planner 8082, Executor 8083 (si présent), PegasusProvider 8084, Dashboard 5000.

## Développement & troubleshooting rapide
- Environnement: créez/activez `venv` puis `pip install -r requirements.txt` (script `start_system.sh` le fait automatiquement si nécessaire).
- Health checks: `curl -s http://localhost:8080/health` (Monitor), vérifier les autres ports analogues.
- Logs et PID: `logs/` et `logs/*.pid` pour arrêter proprement via `stop_system.sh`.
- Activité: plusieurs agents envoient des entrées d'activité au Monitor via `/api/activities/log` (utile pour reproduire workflows et audit).

## Où chercher pour plus de détails
- Prompts & règles d'analyse: `Analyzer/analyzer_rest.py` (PromptManager)
- Règles de planification & commandes: `Planner/planner_rest.py` (PromptBuilder)
- Start / health / examples: `start_system.sh`, `FIXES_APPLIED.md`, `ARCHITECTURE_CHANGES.md`
- Docs de validation et structure: `WorkflowValidator/README.md` et `WorkflowValidator/STRUCTURE.md`

---
Si quelque chose est ambigu ou manque (ex.: conventions non couplées au code), dites-moi quelles sections développer — je les affinerai. ✅
