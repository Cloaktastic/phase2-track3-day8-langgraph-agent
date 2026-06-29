## Project Run & Verification Guide
### Step 1: Environment Setup
Ensure you have installed the dependencies and that your virtual environment is active:
```bash
# Activate your virtual environment (Windows Powershell)
.venv\Scripts\activate

# Install package editably with dev and google dependencies
pip install -e ".[dev,google]"
```

### Step 2: Configure Environment Keys
Rename `.env.example` to `.env` (if not already done) and set your API key :

```ini
cp .env.example .env
```

### Step 3: Run Unit Tests
Run `pytest` to execute all routing, state validation, and graph smoke tests:
```bash
pytest
```

### Step 4: Run Scenario Evaluations
Run the scenario test suite against all 20 built-in test queries. This writes results to `outputs/metrics.json` and updates the lab report:
```bash
make run-scenarios
```

### Step 5: Validate Metrics Schema
Validate the output format and ensure the grading script accepts the metrics:
```bash
make grade-local
```

### Step 6: Run Streamlit UI (Live Interactive Chat)
To chat with the support agent live and handle human-in-the-loop approvals interactively, install Streamlit and run the app:
```bash
pip install streamlit
streamlit run app.py
```
