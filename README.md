# DSE3101-Project

# HDB Resale Price Analysis and Prediction

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Course**: DSE3101 
**Academic Year**: 2025/2026  
**Group Name**: flatfinders

## 📋 Table of Contents
- [Project Overview](#project-overview)
- [Team Members](#team-members)
- [Problem Statement](#problem-statement)
- [Data Sources](#data-sources)
- [Project Structure](#project-structure)
- [Installation & Setup](#installation--setup)
- [Usage](#usage)
- [Methodology](#methodology)
- [Key Features](#key-features)
- [Results](#results)
- [Deliverables](#deliverables)
- [Acknowledgments](#acknowledgments)
- [License](#license)

## 🎯 Project Overview

This project aims to develop a comprehensive analysis and prediction tool for HDB resale prices in Singapore. We combine machine learning models with interactive visualizations to help senior citizens understand pricing dynamics and make informed decisions with respect to downsizing.

**Project Goals:**
- Analyze factors influencing HDB resale prices across Singapore
- Build predictive models for price estimation
- Create an interactive dashboard for exploring downsizing options
- Provide insights for potential buyers and sellers

## 👥 Team Members

### Back-end Team (Modeling & Data Processing)
| Name | Student ID | Role | Responsibilities |
|------|-----------|------|------------------|
| Avaneesh | Team Lead (Backend) | Data collection, model architecture |
| Sanjeev | Data Engineer | Data preprocessing, feature engineering |
| Aswin | ML Engineer | Model training, evaluation |
| Vidushi | Data Analyst | EDA, statistical analysis |

### Front-end Team (Visualization & Interface)
| Name | Student ID | Role | Responsibilities |
|------|-----------|------|------------------|
| [Name 5] | Team Lead (Frontend) | UI/UX design, dashboard architecture |
| [Name 6] | Visualization Developer | Interactive charts, maps |
| [Name 7] | Web Developer | Dashboard implementation |
| [Name 8] | Integration Engineer | Backend-frontend integration |

## 🎯 Problem Statement

Understanding HDB resale prices is crucial for Singapore residents, as HDB flats represent a significant portion of household wealth. This project addresses:

1. **Price Prediction**: Can we accurately predict HDB resale prices based on property characteristics and location?
2. **Market Dynamics**: How do prices vary across towns and over time?
3. **Affordability Analysis**: Which areas offer the best value for different buyer profiles?
4. **Wealth Unlocking**: How much wealth can be unlocked through downsizing or lease buyback schemes?

## 📊 Data Sources

1. **HDB Resale Flat Prices** (2017-2024)
   - Source: [data.gov.sg](https://beta.data.gov.sg/)
   - Records: ~150,000 transactions
   - Features: Town, flat type, floor area, lease commence date, resale price, RPI

2. **Amenities & Infrastructure**
   - Source: [OneMap API](https://www.onemap.gov.sg/)
   - Data: MRT stations, schools, shopping malls, parks
   - Method: Distance calculations via API

3. **Planning Boundaries**
   - Source: [data.gov.sg](https://beta.data.gov.sg/collections/1749/view)
   - Data: Geographical boundaries of planning regions
