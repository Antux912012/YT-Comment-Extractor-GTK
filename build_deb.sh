#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

VERSION="${1:-0.4}"

# 1. Build yt-comment-extractor
STAGE1="${ROOT_DIR}/build/deb_yt_gtk"
rm -rf "${STAGE1}"
mkdir -p "${STAGE1}/DEBIAN" "${STAGE1}/usr/bin" "${STAGE1}/usr/share/applications" "${STAGE1}/usr/share/icons/hicolor/scalable/apps" "${STAGE1}/usr/share/yt-extractor"

cat <<'EOF' > "${STAGE1}/usr/bin/start-yt-extractor"
#!/usr/bin/env bash
export PYTHONPATH="/usr/share/yt-extractor:${PYTHONPATH:-}"
exec python3 /usr/share/yt-extractor/main_gtk.py "$@"
EOF
chmod 755 "${STAGE1}/usr/bin/start-yt-extractor"
ln -sf start-yt-extractor "${STAGE1}/usr/bin/yt-comment-extractor"

install -m 644 "${ROOT_DIR}/io.github.antux912012.YTCommentExtractor.desktop" "${STAGE1}/usr/share/applications/"
install -m 644 "${ROOT_DIR}/io.github.antux912012.YTCommentExtractor.svg" "${STAGE1}/usr/share/icons/hicolor/scalable/apps/"
install -m 644 "${ROOT_DIR}/main_gtk.py" "${ROOT_DIR}/scraper.py" "${STAGE1}/usr/share/yt-extractor/"

cat <<EOF > "${STAGE1}/DEBIAN/control"
Package: yt-comment-extractor
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, yt-dlp | python3-yt-dlp
Maintainer: Antonio <antux912012@users.noreply.github.com>
Homepage: https://github.com/Antux912012/YT-Comment-Extractor-GTK
Description: YouTube Comment Extractor (GTK4 / Libadwaita)
 Graphical utility built with GTK4, Libadwaita, and yt-dlp to extract, filter,
 export, and analyze comments from YouTube videos, including unbiased random
 sampling and CSV export.
EOF

dpkg-deb --build --root-owner-group "${STAGE1}" "${ROOT_DIR}/yt-comment-extractor_${VERSION}_all.deb"
rm -rf "${STAGE1}"

# 2. Build yt-comment-extractor-service
STAGE2="${ROOT_DIR}/build/deb_yt_service"
rm -rf "${STAGE2}"
mkdir -p "${STAGE2}/DEBIAN" "${STAGE2}/usr/bin" "${STAGE2}/usr/share/applications" "${STAGE2}/usr/share/icons/hicolor/scalable/apps" "${STAGE2}/usr/share/yt-extractor-service/templates"

cat <<'EOF' > "${STAGE2}/usr/bin/start-yt-extractor-service"
#!/usr/bin/env bash
export PYTHONPATH="/usr/share/yt-extractor-service:${PYTHONPATH:-}"
cd /usr/share/yt-extractor-service
exec python3 /usr/share/yt-extractor-service/service_manager.py "$@"
EOF
chmod 755 "${STAGE2}/usr/bin/start-yt-extractor-service"
ln -sf start-yt-extractor-service "${STAGE2}/usr/bin/yt-comment-extractor-service"

install -m 644 "${ROOT_DIR}/io.github.antux912012.YTCommentExtractor.Service.desktop" "${STAGE2}/usr/share/applications/"
install -m 644 "${ROOT_DIR}/io.github.antux912012.YTCommentExtractor.Service.svg" "${STAGE2}/usr/share/icons/hicolor/scalable/apps/"
install -m 644 "${ROOT_DIR}/icon.png" "${ROOT_DIR}/scraper.py" "${ROOT_DIR}/service_manager.py" "${ROOT_DIR}/web_app.py" "${STAGE2}/usr/share/yt-extractor-service/"
install -m 644 "${ROOT_DIR}/templates/index.html" "${STAGE2}/usr/share/yt-extractor-service/templates/index.html"

cat <<EOF > "${STAGE2}/DEBIAN/control"
Package: yt-comment-extractor-service
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-flask, python3-werkzeug, python3-zeroconf, python3-pil, python3-pystray, python3-gi, gir1.2-gtk-3.0, yt-dlp | python3-yt-dlp
Maintainer: Antonio <antux912012@users.noreply.github.com>
Homepage: https://github.com/Antux912012/YT-Comment-Extractor-GTK
Description: YouTube Comment Extractor Background Service & Web UI
 Background web server and system tray indicator service for YouTube Comment
 Extractor, providing a local browser dashboard for automated comment scraping.
EOF

dpkg-deb --build --root-owner-group "${STAGE2}" "${ROOT_DIR}/yt-comment-extractor-service_${VERSION}_all.deb"
rm -rf "${STAGE2}"
echo "==> Built yt-comment-extractor and yt-comment-extractor-service v${VERSION}"
