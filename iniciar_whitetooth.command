#!/bin/bash
# Script de inicio directo para Whitetooth en macOS
cd "$(dirname "$0")"

# Liberar puerto 8000 si quedó algún proceso colgado anterior
lsof -ti :8000 | xargs kill -9 2>/dev/null

echo "Iniciando Whitetooth Clínica Dental..."
./venv/bin/python3 run.py
