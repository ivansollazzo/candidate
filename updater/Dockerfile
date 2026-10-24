FROM docker:27-cli
# Fallback for a project folder without the script; normally the one in the project folder runs,
# so updates of the script apply without rebuilding this image
COPY updater.sh /updater.sh
ENTRYPOINT ["sh", "-c", "[ -f /project/updater/updater.sh ] && exec sh /project/updater/updater.sh; exec sh /updater.sh"]
