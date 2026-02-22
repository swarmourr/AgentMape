# ⚠️ NOTE: This Directory Is NOT Used

## This `common/` directory was created initially but is NOT the approach we're using.

### ✅ ACTUAL IMPLEMENTATION

Instead of a common directory, we integrate logging directly into each component with their **existing databases**:

1. **Analyzer** → Uses `Analyzer/interaction_logger.py` with `analyzer_agent_db.json`
2. **Planner** → Uses `Planner/interaction_logger.py` with `planner_db.json`
3. **PegasusProvider** → Uses `PegasusProvider/interaction_aggregator.py` to collect from both

### 📚 See the Real Integration Guides

- **Main Guide:** `/Users/hamzasafri/Desktop/AgentMape/LLM_INTERACTION_LOGGING_GUIDE.md`
- **Analyzer:** `Analyzer/INTERACTION_INTEGRATION.md`
- **Planner:** `Planner/INTERACTION_INTEGRATION.md`
- **PegasusProvider:** `PegasusProvider/INTERACTION_INTEGRATION.md`

### Why Not Common?

You requested:
1. ✅ Each component should have its own logging (not common)
2. ✅ Use existing databases (not new files)
3. ✅ PegasusProvider should aggregate from all sources
4. ✅ Handle duplicate workflow IDs by returning latest

The files in this `common/` directory can be safely ignored or deleted.

### 🎯 What To Use Instead

```
Analyzer/interaction_logger.py          ← Use this
Planner/interaction_logger.py           ← Use this
PegasusProvider/interaction_aggregator.py ← Use this
```

NOT the files in `common/`.
