# Makefile for Credit Risk Modelling Pipeline

PYTHON = python

.PHONY: all clean test data models stress report slides

all: data models stress test

data:
	$(PYTHON) -m src.credit.data_macro.extract_macro
	$(PYTHON) -m src.credit.data_ratings.extract_ratings
	$(PYTHON) -m src.credit.data_fund.extract_fundamentals
	$(PYTHON) -m src.credit.panel.build_panel

models:
	$(PYTHON) -m src.credit.models_ordinal.fit_ordinal
	$(PYTHON) -m src.credit.models_ordinal.shadow_rating
	$(PYTHON) -m src.credit.models_binary.fit_fallen_angel
	$(PYTHON) -m src.credit.models_binary.early_warning

stress:
	$(PYTHON) -m src.credit.stress.var_scenarios
	$(PYTHON) -m src.credit.stress.run_scenarios

report:
	$(PYTHON) -m src.credit.reporting.generate_report

slides:
	$(PYTHON) -m src.credit.reporting.build_presentation

test:
	$(PYTHON) -m pytest tests/ -v
