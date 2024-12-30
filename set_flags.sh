#!/bin/bash

# Exit if no input parameter is provided
if [ -z "$1" ]; then
  echo "No language parameter provided. Exiting."
  exit 1
fi

flink=$(readlink -f folder.jpg)
creatortool=$(exiftool -f -s3 -"creatortool" "$flink")
widthfolder=$(exiftool -f -s3 -"ImageWidth" "$flink")
widthposter=$(expr $widthfolder / 5)

# Directory containing flag images
flag_dir="/mnt/temp2/flags"
temp_flag_dir="/mnt/temp2/flags/tmp"

# Create temp directory for resized flags
mkdir -p "$temp_flag_dir"

# Split input parameter into an array (assuming input is separated by underscores "_")
IFS="_" read -r -a input_flags <<< "$1"

# Process flags in the input order
for flag_code in "${input_flags[@]}"; do
  flag_path="$flag_dir/$flag_code.png"

  # Check if the flag image exists
  if [ -f "$flag_path" ]; then
    # Resize the flag and save to temp directory
    convert "$flag_path" -resize "$widthposter" "$temp_flag_dir/${flag_code}_tmp.png"
  else
    echo "Flag image for '$flag_code' not found. Skipping."
  fi
done

# Check if any temporary flag files exist
if [ -z "$(ls -A "$temp_flag_dir" 2>/dev/null)" ]; then
  echo "No matching flags found. Exiting."
  rm -rf "$temp_flag_dir"
  exit 1
fi

# Create montage of resized flags in the order of input
montage "$temp_flag_dir"/*_tmp.png -geometry +8+8 -tile 1x4 -background transparent "$temp_flag_dir/test.png"

# Overlay montage onto the original image
convert "$flink" "$temp_flag_dir/test.png" -flatten "$flink"

# Set file permissions and metadata to avoid re-writing
chmod +644 "$flink"
chown nobody "$flink"
exiftool -creatortool="993" -overwrite_original "$flink"

# Clean up temporary files
rm -rf "$temp_flag_dir"

echo "Flags added successfully"
