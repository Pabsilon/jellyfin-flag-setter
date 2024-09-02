#!/bin/bash
flink=$(readlink -f folder.jpg)
creatortool=$( exiftool -f -s3 -"creatortool" "$flink")
widthfolder=$( exiftool -f -s3 -"ImageWidth" "$flink" )
widthposter=$(expr $widthfolder / 5)

case $1 in

  *es*)
    convert /mnt/temp2/flags/es.png -resize "$widthposter" /mnt/temp2/flags/es_tmp.png
  ;;&

  *gb*)
    convert /mnt/temp2/flags/gb.png -resize "$widthposter" /mnt/temp2/flags/gb_tmp.png
  ;;&

  *jp*)
    convert /mnt/temp2/flags/jp.png -resize "$widthposter" /mnt/temp2/flags/jp_tmp.png
  ;;&

  *de*)
    convert /mnt/temp2/flags/de.png -resize "$widthposter" /mnt/temp2/flags/de_tmp.png
  ;;&

  *fr*)
    convert /mnt/temp2/flags/fr.png -resize "$widthposter" /mnt/temp2/flags/fr_tmp.png
  ;;

esac

montage /mnt/temp2/flags/*_tmp.png -geometry +8+8 -tile 1x4 -background transparent /mnt/temp2/flags/test.png
convert  "$flink"  /mnt/temp2/flags/test.png -flatten  "$flink"
chmod +644 "$flink"
chown nobody "$flink"
exiftool -creatortool="993" -overwrite_original "$flink"
rm /mnt/temp2/flags/*_tmp.png
