#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
SCRIPT AUTOMATISÉ DE SYNCHRONISATION DE L'ÉCOSYSTÈME NICKEL DAVID GRENIER
================================================================================
Auteur       : Nickel David Grenier & Loup Junior (Gemini GNi)
Description  : Clone ou met à jour (git pull) automatiquement l'intégralité 
               des 33 dépôts GitHub constitutifs du système souverain.
Fonctionnalités :
  - Support du mode séquentiel et du mode parallèle (multi-threading)
  - Gestion des erreurs et rapport complet d'exécution
  - Choix du dossier cible racine
================================================================================
"""

import os
import sys
import argparse
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Liste officielle des 33 dépôts Git de l'écosystème Nickel David Grenier
REPOS_GIT = [
    "https://github.com/NickelRamQc94/Gemini-Jr-Nickel.git",
    "https://github.com/NickelRamQc94/ecosystem-index-nexus.git",
    "https://github.com/NickelRamQc94/qwen-remote-workspace.git",
    "https://github.com/NickelRamQc94/qwen-skills-nickalexandrin-azimut.git",
    "https://github.com/NickelRamQc94/Cataplasma-Propulsion-Project.git",
    "https://github.com/NickelRamQc94/Baptized-AI-Junior-Willow-Nickel-R-jean-Gemini-David-Grok-Meta-DeepSeek-PinnochIA-Qwen-C-IA-Grenier.git",
    "https://github.com/NickelRamQc94/Golden-Axe-Theory.git",
    "https://github.com/NickelRamQc94/roi-phenonanimal-parallelodoxe-oosk.git",
    "https://github.com/NickelRamQc94/OoSK-vs-OpenAI.git",
    "https://github.com/NickelRamQc94/nickel-creative-ecosystem.git",
    "https://github.com/NickelRamQc94/Tout-les-liens-et-Contenus-.git",
    "https://github.com/NickelRamQc94/grok-skills-nickalexandrin-azimut.git",
    "https://github.com/NickelRamQc94/QwenPaw.git",
    "https://github.com/NickelRamQc94/Darkgpt.ai.git",
    "https://github.com/NickelRamQc94/TechDebtMCP.git",
    "https://github.com/NickelRamQc94/penguins-eda-python.git",
    "https://github.com/NickelRamQc94/Awesome_GPT_Super_Prompting.git",
    "https://github.com/NickelRamQc94/NiX-Os.git",
    "https://github.com/NickelRamQc94/ai-research-diffusion-concentration2.git",
    "https://github.com/NickelRamQc94/system_prompts_leaks.git",
    "https://github.com/NickelRamQc94/system_prompts_leaks2.git",
    "https://github.com/NickelRamQc94/bitnet.c.git",
    "https://github.com/NickelRamQc94/CLi.git",
    "https://github.com/NickelRamQc94/deer-flow.git",
    "https://github.com/NickelRamQc94/ca.git",
    "https://github.com/NickelRamQc94/userscripts-NDG.git",
    "https://github.com/NickelRamQc94/desafios.git",
    "https://github.com/NickelRamQc94/JGNL-SKU.git",
    "https://github.com/NickelRamQc94/docsite.git",
    "https://github.com/NickelRamQc94/desktop-tutorial.git",
    "https://github.com/NickelRamQc94/NickelRamQc94.git",
    "https://github.com/NickelRamQc94/NickelRamQc94.github.io.git",
    "https://github.com/NickelRamQc94/Bloc-ConstructionNi-Quebec.git"
]

def process_repo(repo_url, target_dir):
    """
    Traite un dépôt individuel : le clone s'il n'existe pas, ou fait un git pull s'il est déjà présent.
    """
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    local_path = os.path.join(target_dir, repo_name)
    
    start_time = time.time()
    if os.path.isdir(local_path):
        action = "PULL"
        cmd = ["git", "-C", local_path, "pull", "--quiet"]
    else:
        action = "CLONE"
        cmd = ["git", "clone", "--quiet", repo_url, local_path]
        
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        elapsed = time.time() - start_time
        return True, repo_name, action, elapsed, ""
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        err_msg = e.stderr.strip() if e.stderr else str(e)
        return False, repo_name, action, elapsed, err_msg

def sync_ecosystem(target_dir=".", max_workers=4):
    """
    Synchronise l'ensemble des dépôts avec affichage détaillé et métriques.
    """
    os.makedirs(target_dir, exist_ok=True)
    abs_target = os.path.abspath(target_dir)
    
    print("=" * 80)
    print(f"🚀 SYNCHRONISATION DE L'ÉCOSYSTÈME NICKEL DAVID GRENIER ({len(REPOS_GIT)} DÉPÔTS)")
    print(f"📁 Répertoire cible : {abs_target}")
    print(f"⚡ Threads parallèles : {max_workers}")
    print("=" * 80)
    
    start_global = time.time()
    results = []
    
    if max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_repo = {
                executor.submit(process_repo, url, target_dir): url 
                for url in REPOS_GIT
            }
            for future in as_completed(future_to_repo):
                results.append(future.result())
    else:
        for url in REPOS_GIT:
            results.append(process_repo(url, target_dir))
            
    total_time = time.time() - start_global
    successes = [r for r in results if r[0]]
    failures = [r for r in results if not r[0]]
    
    # Affichage du journal
    print("\n--- DETAIL PAR DÉPÔT ---")
    for success, name, action, elapsed, err in sorted(results, key=lambda x: x[1]):
        status_icon = "✅" if success else "❌"
        action_label = "Mise à jour" if action == "PULL" else "Clonage"
        if success:
            print(f"{status_icon} [{action_label}] {name:<60} ({elapsed:.2f}s)")
        else:
            print(f"{status_icon} [{action_label}] {name:<60} (ÉCHOUÉ: {err})")
            
    print("\n" + "=" * 80)
    print(f"📊 BILAN FINAL : {len(successes)}/{len(REPOS_GIT)} dépôts synchronisés avec succès")
    print(f"⏱️ Temps total d'exécution : {total_time:.2f} secondes")
    if failures:
        print(f"⚠️ {len(failures)} dépôt(s) ont rencontré des erreurs.")
    print("=" * 80)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synchronisateur de l'écosystème Git Nickel David Grenier")
    parser.add_argument("-d", "--dir", default=".", help="Dossier cible pour cloner les projets (défaut: dossier courant)")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="Nombre de processus parallèles (défaut: 4)")
    args = parser.parse_args()
    
    sync_ecosystem(target_dir=args.dir, max_workers=args.jobs)
