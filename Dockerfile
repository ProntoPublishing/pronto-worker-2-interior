# Worker 2 - Interior PDF Generator
# Requires: Python, Pandoc, XeLaTeX, fonts

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    pandoc \
    texlive-xetex \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-latex-extra \
    fonts-liberation \
    fonts-dejavu \
    fonts-ebgaramond \
    fonts-ebgaramond-extra \
    fonts-linuxlibertine \
    fonts-urw-base35 \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Remove WOFF font variants — xdvipdfmx cannot embed WOFF, only TTF/OTF.
# Debian's fonts-ebgaramond installs both; fontconfig may resolve italic
# to the WOFF file, which aborts xelatex at PDF-generation time.
RUN rm -rf /usr/share/fonts/woff \
 && rm -rf /var/cache/fontconfig/* \
 && rm -rf /root/.cache/fontconfig \
 && fc-cache -fv

# Replace the package's UNFINISHED Bold (v0.016, 127 glyphs — no
# em-dash / curly quotes / en-dash / ellipsis; renders tofu in every
# bold heading and TOC row) with the complete v1.002 Bold from the
# maintained EB Garamond continuation (2,091 glyphs, OFL — see
# fonts/README.md). Same filename on purpose: the templates pin this
# exact path, so the swap fixes both templates with zero template diff.
COPY fonts/EBGaramond12-Bold.otf /usr/share/fonts/opentype/ebgaramond/EBGaramond12-Bold.otf
RUN fc-cache -f

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "app.py"]
