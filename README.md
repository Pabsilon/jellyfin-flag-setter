# On the archivation of this project

This project was my way of working around Jellyfin's lack of search by audio language. Ever since the release of v12.0 of jellyfin, this is now achievable and the project loses it's main appeal to me.
I understand that it could be used to tag thinks like 4k movies, HDR, etc.. , and that in general someone could find a use for it. You are more than welcome to fork and take over, or just reimplement the general idea.

As a side-note; this is NOT copatible with Jellyfin v12.0 or higher, so it does need some changes.

# Jellyfin Flag Setter

This is a flag setter for jellyfin posters. Please use with caution since it runs destructive jobs against your posters.

### Current known issues
- None that I know of. PLease report any issues.

# 🤖 Disclaimer

This project was 100% vibecoded using Claude Code with Sonnet 4.6 & Opus 4.7 under my supervision.

I am a full time back-end developper and I wanted to see how far these tools have come. They're doing pretty good if you ask me.

# Project Info

![Edit preview](.github/images/preview.png)

It features:

- Automatic mapping from Audio metadata to flags (languages - flag mappings can be configured).
- A local database that keeps track of edited files (the daily job does a deep scan and finds any posters that are reverted).
- Metadata edition to actually know if the file was edited or not.
- Two sync jobs (Recently added (15min)/ Full Scan (24h)) with configurable schedules.

----

## Jobs

![Jobs](.github/images/jobs.png)

### Library Sync
This is a job that runs once every 24h and fetches all images to update their status.

### Recent Sync
The recent sync job runs by default every 15 minutes to scan for recently added media.

------------

# Deployment

The recommended way of running it is with docker. (Specially, docker-compose)

`docker-compose.yml`

```
services:
  jellyfin-flag-setter:
    image: ghcr.io/pabsilon/jellyfin-flag-setter:latest
    restart: unless-stopped
    ports:
      - 8000:8000
    env_file: .env
    volumes:
      - .:/app/data
networks: {}
```

`.env` file

```
JELLYFIN_URL=http://your-jellyfin-host:8096
JELLYFIN_API_KEY=your_api_key_here

# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your_secret_key_here

# Path to the SQLite database file (Don't change it)
DB_PATH=data/flagsetter.db
```

On first startup, it will run a job to fetch all the libraries in your server. It might take a while depending on the size of your library.

Once the job is ready, the first setup will ask you to create a user and password.
