# Corpus provenance — Sloth Drawer
#
# Every manual in data/manuals/ is a public, freely downloadable manufacturer
# PDF. The manuals themselves are gitignored (they are not ours to
# redistribute); this file records where each one came from, so the demo is
# reproducible and the post can cite its sources.
#
# Device class: air purifiers. One class = one card layout = a coherent demo.
# Collected: 2026-10-22.
#
# Columns: device_slug | brand | model | source_url | pages | text_chars | status
#
# 31 candidates were fetched. 19 became the corpus. The 12 that did not are
# listed below with the reason, because the skipped files are part of the
# honest story: 4 have no text layer at all, 6 were blocked by the host, and 2
# could not be parsed by pypdf.

## --- the corpus (19 manuals) ---

coway-airmega-100 | Coway | Airmega 100 | https://coway.se/wp-content/uploads/2024/07/9244339_Airmega_100_____001__24.02.20_-pages-1.pdf | 19 | 18585 | kept
coway-airmega-400s | Coway | Airmega 400S/400/300S/300 | https://images-na.ssl-images-amazon.com/images/I/D1SWYNC4nwS.pdf | 36 | 37562 | kept
levoit-core-200s-plus | Levoit | Core 200S Plus | https://images.thdstatic.com/catalog/pdfImages/25/2582fa13-fa24-46d2-b708-d35499636c29.pdf | 20 | 29170 | kept
levoit-essential-200s | Levoit | Essential 200S | https://images-na.ssl-images-amazon.com/images/I/A1fPaff4UwL.pdf | 16 | 12657 | kept
honeywell-hpa3000 | Honeywell | HPA3100/HPA3200/HPA3300 | https://www.honeywellpluggedin.com/wp-content/uploads/HPA3000_Series_OM_ENG_US_A008456R0_r3_4OCT2023.pdf | 13 | 19888 | kept
honeywell-insight-hpa5100 | Honeywell | InSight HPA5100-HPA5300 | https://www.honeywellstore.com/store/images/pdf/hpa5100-to-hpa5300-honeywell-insight-hepa-air-purifier-manual.pdf | 33 | 68136 | kept
honeywell-hpa8350 | Honeywell | HPA8350 | https://prod-edam.honeywell.com/content/dam/honeywell-edam/hbt/en-us/documents/manuals-and-guides/installation-guides/HBT-BMS-hpa8350-air-purifier-manual.pdf | 11 | 24534 | kept
blueair-blue-pure-211a | Blueair | Blue Pure 211+ Auto | https://www.williams-sonoma.com/netstorage/pdf/Blue-Pure-211-Auto-User-Manual-106598-EN-F-ES-rev-000.pdf | 56 | 43360 | kept
blueair-health-protect-7300 | Blueair | HealthProtect 7300/7400/7500/7700 | https://www.luftrenare.se/documents/HealthProtect%20User%20Manual%20EU_ME_SEA%20rev003.pdf | 352 | 337580 | kept
medify-ma-112 | Medify | MA-112 | https://www.montgomeryschoolsmd.org/siteassets/district/departments/facilities/medify_air-112_manual.pdf | 11 | 17814 | kept
medify-ma-25 | Medify | MA-25 | https://images.thdstatic.com/catalog/pdfImages/53/53c17e64-2043-4b7f-81c4-3d0aff67f2cc.pdf | 10 | 9041 | kept
medify-ma-40 | Medify | MA-40 | https://www.airpurifiersandcleaners.com/files/4281506/uploaded/Medify_Air_-_MA-40_-_Product_Manual.pdf | 12 | 10613 | kept
medify-ma-14 | Medify | MA-14 | https://images.thdstatic.com/catalog/pdfImages/64/64e055e4-d7ee-4f3f-9752-929c20c7096f.pdf | 10 | 10651 | kept
winix-5500 | Winix | 5500-2 | https://www.winixamerica.com/wp-content/uploads/2022/07/User-Manual_5500-2.pdf | 2 | 17382 | kept
winix-6300 | Winix | 6300-2 | https://www.winixamerica.com/wp-content/uploads/2022/01/6300-2_User-Manual_Web.pdf | 2 | 19263 | kept
winix-a230 | Winix | A230/A231 | https://www.winixamerica.com/wp-content/uploads/2022/07/User-Manual_A230-A231.pdf | 2 | 8863 | kept
winix-am90 | Winix | AM90 | https://www.winixamerica.com/wp-content/uploads/2022/07/User-Manual_AM90.pdf | 2 | 15244 | kept
winix-c545 | Winix | C545 | https://www.winixamerica.com/wp-content/uploads/2022/03/C545_User-Manual2610-0256-00.pdf | 2 | 15436 | kept
winix-c610 | Winix | C610 | https://www.winixamerica.com/wp-content/uploads/2024/09/C610_User-Manual.pdf | 2 | 15305 | kept

## --- skipped, with the reason ---

## No text layer. Image-only scans: pypdf extracts 0 characters. These are the
## manuals a PDF tool that only reads pixels cannot help with.
coway-airmega-100-fi | Coway | Airmega 100 | https://www.allergia-apu.fi/files/products/Airmega-100-Manual095394600-1730360517.pdf | 9 | 0 | skipped:no_text_layer
honeywell-hpa250 | Honeywell | HPA250 | https://prod-edam.honeywell.com/content/dam/honeywell-edam/hbt/en-us/documents/manuals-and-guides/installation-guides/HBT-BMS-HPA250-Blue-Tooth-Air-Purifier-Manual.pdf | 8 | 0 | skipped:no_text_layer
levoit-core-300 | Levoit | Core 300 | https://m.media-amazon.com/images/I/B1UQQIW5olL.pdf | 20 | 0 | skipped:no_text_layer
levoit-core-300s | Levoit | Core 300S | https://files.vesync.com/desc/LEVOIT_Core300S_USER_MANUAL.pdf | 24 | 0 | skipped:no_text_layer

## Blocked by the host. HTTP 403 on fetch: the file was never downloaded, so
## it was never a candidate for the corpus.
coway-ap-1512hh | Coway | AP-1512HH | http://www.ntsupply.com/files/products/AP-1512HH.pdf | - | - | skipped:http_403
blueair-health-protect-3210 | Blueair | Health Protect 3210-3410 | https://www.clemas.co.uk/wp-content/uploads/Blueair-Blue-Range-3210-3410-user-manual.pdf | - | - | skipped:http_403
blueair-pro-m | Blueair | Pro M | https://www.natlallergy.com/images/art/Blueair-Pro-Air-Purifier-Manual.pdf | - | - | skipped:http_403
blueair-comfortpure-t10i | Blueair | ComfortPure T10i | https://fc.darty.com/notices/6/9/3/d/693df0e346ff028a9a28ec235e37ee3d3a505876.pdf | - | - | skipped:http_403
blueair-classic-505 | Blueair | Classic 505/605 | https://www.achooallergy.com/user_manuals/Blueair_User_Manuals_505_605_Series.pdf | - | - | skipped:http_403
blueair-joy-s | Blueair | Joy S | https://www.sleepsolutions.com.au/amfile/file/download/file/175/product/5873/ | - | - | skipped:http_403
winix-9500 | Winix | 9500/9300 | https://www.natlallergy.com/images/art/Winix%20Air%20Purifier%209500-9300-User-Manual.pdf | - | - | skipped:http_403

## Unreadable by pypdf. One file could not be opened at all.
airthereal-aph260 | Airthereal | APH260 | https://images-na.ssl-images-amazon.com/images/I/A1AGuwDK28L.pdf | - | - | skipped:unreadable_pdf
