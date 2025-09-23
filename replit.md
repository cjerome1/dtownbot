# Bot Discord D-TOWN ROLEPLAY

## Vue d'ensemble

Bot Discord officiel pour le serveur D-TOWN ROLEPLAY, serveur français FiveM du Canada. Le bot offre une interface complète avec commandes slash et menu interactif pour faciliter l'interaction avec la communauté.

## État actuel

✅ **Bot opérationnel** - Connecté et fonctionnel  
✅ **Toutes les fonctionnalités implémentées**  
✅ **Interface française complète**  
✅ **Optimisé pour hébergement local/serveur dédié**  

## Fonctionnalités principales

### Commandes slash disponibles

- `/regles` - Affiche les règles du serveur et lien vers le canal des règles
- `/serveur` - Vérifie le statut du serveur FiveM en temps réel
- `/tebex` - Lien vers la boutique officielle du serveur
- `/f8connect` - Instructions de connexion F8 avec IP du serveur
- `/menu` - Menu interactif principal avec boutons

### Caractéristiques techniques

- **Statut automatique** : Mise à jour du statut toutes les 5 minutes
- **Monitoring serveur** : Vérification du serveur FiveM (148.113.219.113)
- **Interface interactive** : Menu avec boutons Discord natifs
- **Embeds riches** : Messages formatés avec couleurs et icônes
- **Gestion d'erreurs** : Messages d'erreur informatifs en français

## Configuration du serveur

### Informations du serveur FiveM
- **IP** : 148.113.219.113
- **Port** : 30120 (standard FiveM)

### Canaux Discord
- **Canal des règles** : ID 1365802245551161424

### Services externes
- **Boutique Tebex** : https://d-town-roleplay.tebex.io

## Architecture du projet

### Fichiers principaux
- `main.py` - Bot principal avec toutes les commandes et fonctionnalités
- `config.json` - Configuration centralisée (couleurs, URLs, IDs)
- `replit.md` - Documentation du projet

### Sécurité
- Token Discord géré via variables d'environnement Replit
- Aucun secret dans les fichiers du projet
- Intents minimaux pour éviter les permissions privilégiées

## Modifications récentes

**22 septembre 2025**
- Création complète du bot Discord D-TOWN ROLEPLAY
- Implémentation de toutes les commandes slash demandées
- Configuration du statut automatique avec monitoring FiveM
- Création du menu interactif avec boutons
- Optimisation des performances et correction des erreurs d'affichage
- Mise en production avec hébergement Replit

## Préférences utilisateur

- **Interface** : 100% en français pour serveur canadien
- **Hébergement** : Local ou serveur dédié (pas de dashboard web)
- **Fonctionnalités** : Focus sur les commandes Discord natives
- **Performance** : Code optimisé et bien structuré

## Notes de déploiement

Le bot est configuré pour fonctionner immédiatement sur :
- Hébergement local (avec Python 3.11+)
- Serveur dédié 
- Plateforme cloud Replit

**Prérequis :**
- Token Discord valide (variable DISCORD_BOT_TOKEN)
- Bot invité sur le serveur avec permissions slash commands
- Python 3.11+ avec discord.py installé