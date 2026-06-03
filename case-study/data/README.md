# Data

The analysis runs on **UCI Online Retail II**, a real transaction ledger from a
UK-registered online retailer (01 Dec 2009 to 09 Dec 2011, ~1.07m line items).

The raw file (~45 MB) is **not committed** to keep the site repository light.
To reproduce the analysis, download it first:

```bash
curl -L -o online_retail_II.zip \
  "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
unzip online_retail_II.zip          # -> online_retail_II.xlsx
```

Then run the analysis from the project root:

```bash
python3 case-study/notebook/measurement_integrity_audit.py
```

Source: https://archive.ics.uci.edu/dataset/502/online+retail+ii
Citation: Chen, D. (2019). Online Retail II. UCI Machine Learning Repository.
