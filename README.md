# Jellyfin Flag Setter

This is a _very_ work in progress and experimental project for setting flags to jellyfin posters.




# OLD VERSION - Script only
Check the `old` branch for the old script.
## Requirements:

libimage-exiftool-perl

To install it, run:

```
sudo apt install libimage-exiftool-perl
```

### Disclaimer:

The script is provided as-is, and might (mostly will) require fine-tuning.

In the script, update the two values in lines 15 & 16 in order to reflect where your flag png reference files reside, and what temp folder you will use.

In my case, the script resides in **/mnt/temp2/flags**.

This is residing on a Debian 12 machine, and my jellyfin instance is running the latest image in docker. 

**You need to change the routes depending where your script, and the flags pngs reside.**

### Jellyfin configuration

Jellyfin usually stores the posters for the images in a different folder. You can make it so that the images are stored alongside the file:

Go to Dashboard -> Libraries -> Libraries -> [Library] -> Manage Library

In Image Fetchers, tick the "Save artwork into media folders".

Refreshing all metadata of the library (including images) will make it so that a collection of images are stored alongside the file: backdrop.jpg, folder.jpg, logo.png. We're deliberately targetting 'folder.jpg' which is the image used in the gallery.

### Usage

Move the set_flags.sh script to /usr/bin so that it's always available in your path. (You might need to re-login again)

Go to the folder containing your media that requires the image modified.

Run:

```set_flags.sh es_gb```

to set the Spanish and UK flags.

The order of flags is determined by the script. Flags can be added by adding them as .png files to the flags forlder (I recommend a width of 160 pixels for the flags, I sourced mine from [here](https://flagpedia.net/download/icons).

### Thanks to:

ProductRockstar in [reddit](https://www.reddit.com/r/jellyfin/comments/11dgmp3/script_to_add_language_overlay_to_movie_poster/) for inspiring this script.
