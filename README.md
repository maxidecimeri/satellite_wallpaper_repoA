# Satellite Wallpaper (Early Stage)

⚠️ **Work in Progress — Personal Project**  
This repository contains early-stage code and configurations for a personal wallpaper automation system.  
Not intended for distribution or public use at this time.

## Overview
This project fetches, processes, and manages satellite images for use as desktop wallpapers.  
It automates retrieval from publicly available sources, organizes them locally, and provides scripts to set and rotate wallpapers.

## Features
- Fetches publicly available satellite imagery.
- Places images in a local `wallpapers/` directory (ignored in version control).
- Utilities for:
  - Static wallpaper setting.
  - Image metadata handling.
  - Generating supplementary data from filenames or CSVs.
- Example configuration files for customization.

## Repository Structure
- `deploy-wallpaper.py` – Deploys wallpapers to desktop monitors.
- `fetch_wallpapers.py` – Retrieves satellite images (primary fetch script).
- `config_example.json` – Example configuration file.
- `wallpaper_daemon.py` – Manages ongoing wallpaper rotation.
- `embed_geo_from_csv.py` – Embeds geodata into image files from CSV input.
- `regen_places_from_filenames.py` – Regenerates location data based on image filenames.
- `views_config.json` – Configuration for display layout and views.

## Setup
1. Clone the repository.
2. Create and activate a Python virtual environment (not included in repo):
   ```bash
   python -m venv satellite-wallpaper-env
   source satellite-wallpaper-env/bin/activate   # Linux/Mac
   .\satellite-wallpaper-env\Scripts\activate    # Windows
