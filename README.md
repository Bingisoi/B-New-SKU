# Bimbo GTM Signal Intelligence Pipeline

An automated GTM intelligence pipeline designed to identify high-value retail and market signals that can be used to support signal-led outbound and account prioritization.

## 🎯 Project Overview

The goal of this project was to build a system that turns unstructured web information into actionable GTM signals.

Instead of relying on static account lists, the pipeline looks for events such as:

* Store expansion
* New retail locations
* Hiring and leadership changes
* Distribution expansion
* Procurement activity
* Acquisitions
* Capital investment
* Bakery and food-sector activity

These signals can then be enriched and prioritized in Clay for targeted outbound campaigns.

## 🏗️ Pipeline Architecture

```text
Web / Search Discovery
        ↓
URL Discovery
        ↓
URL Cleaning & Validation
        ↓
Web Scraping
        ↓
Content Cleaning
        ↓
Signal Detection
        ↓
Signal Classification
        ↓
Structured GTM Data
        ↓
Clay
        ↓
Account Prioritization
        ↓
Signal-Led Outreach
```

## 🛠️ Tech Stack

* Python
* ZenRows
* Clay
* Apollo
* Crawl4AI
* CSV / JSON / JSONL
* Regular expressions
* Web data extraction
* AI-assisted signal classification

## 📊 Current Pipeline

The discovery stage identified **231 unique URLs** across relevant retail, grocery, bakery and business sources.

The scraping layer was used to collect page content and metadata.

The processing layer converts the scraped content into structured fields including:

```text
source_url
scrape_status
page_title
page_type
signal_keywords
signal_context
```

These fields can then be passed into Clay for deeper AI-based signal extraction and account prioritization.

## 🔎 Example GTM Signals

Example signals the system is designed to identify:

### Store Expansion

A retailer announces multiple new stores in a target market.

**Potential GTM implication:**
New locations may create opportunities for additional product distribution, category expansion or retail partnerships.

### Hiring

A company opens a Category Manager, Bakery Buyer or Procurement role.

**Potential GTM implication:**
A new decision-maker or expanding team can indicate increased purchasing or category activity.

### Distribution Expansion

A retailer announces a new distribution center or warehouse.

**Potential GTM implication:**
Distribution investment can indicate increasing geographic coverage and potential supplier opportunities.

## 📦 Output Structure

The final signal layer can be structured into fields such as:

```text
company
company_type
industry
location
signal_type
signal
signal_date
context
evidence
why_it_matters
potential_need
decision_maker_roles
bimbo_relevance
confidence
signal_strength
priority
source_url
```

## 💡 Why This Matters for GTM

Traditional outbound often starts with:

> Find companies → find contacts → send emails

This project flips the process:

> Find meaningful business events → identify companies affected → identify relevant decision-makers → personalize outreach around the event

This creates a **signal-led GTM workflow** rather than a generic prospecting list.

## 🚀 Potential Production Workflow

The pipeline could be extended into:

```text
Web Signals
    ↓
Python / Scraping
    ↓
Clay Enrichment
    ↓
AI Signal Classification
    ↓
ICP Scoring
    ↓
Decision-Maker Identification
    ↓
Personalized Messaging
    ↓
Instantly / Outreach
    ↓
CRM
```

## 📁 Repository Structure

```text
bimbo-signals/
│
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── src/
│   ├── bimbo_signal_pipeline.py
│   ├── bimbo_pipeline.py
│   ├── clean_urls.py
│   └── zenrows_fetch.py
│
├── prompts/
│   └── signal_extraction_prompt.md
│
└── examples/
    └── sample_signal.json
```

## 🔐 Security

API keys and credentials are intentionally excluded from this repository.

Create a local `.env` file for API credentials and never commit it to GitHub.

## 📌 Portfolio Context

This project demonstrates how I approach GTM engineering:

**Research → Data → Automation → Signals → Prioritization → Outreach**

The objective is not simply to collect more leads, but to identify **why an account may be worth contacting now**.
