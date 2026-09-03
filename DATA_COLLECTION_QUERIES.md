# Amazon collection plan

Use the same domain as the crawler configuration and URL-encode each query:

`https://www.amazon.com/s?k=<url-encoded-query>`

The 20 queries below intentionally overlap slightly. Overlap is useful for
quality because it lets the pipeline merge a detailed product-page record with
a search-result record instead of treating them as separate products.

1. `laptop`
2. `gaming laptop`
3. `AI laptop`
4. `business laptop`
5. `student laptop`
6. `RTX 3050 gaming laptop`
7. `RTX 4060 gaming laptop`
8. `2 in 1 laptop`
9. `desktop computer`
10. `mini PC computer`
11. `all in one computer`
12. `computer monitor 24 inch`
13. `4K computer monitor`
14. `mechanical keyboard`
15. `wireless keyboard`
16. `gaming keyboard`
17. `wireless mouse`
18. `gaming mouse`
19. `webcam for computer`
20. `unlocked android smartphone`

For roughly 1,000–2,000 unique products, collect 50–100 results per query
across multiple result pages, then deduplicate by ASIN. The target is not
2,000 rows per query: the same ASIN will appear in overlapping searches.

## Quality gates

The crawler should retain the full raw response, but a product becomes
`ready` only when it has an ASIN, title, price, currency, stock state, category,
and at least one image. Products missing price or delivery data remain
`partial` for browsing and details, but are excluded from budget filtering and
Razorpay checkout.

Run the normalizer after each crawl:

```bash
python catalog_pipeline.py --dry-run
python catalog_pipeline.py --kinds laptop,desktop,keyboard,mouse,mobile,tablet,monitor,headphone,camera,storage,networking,accessory
python index_products.py
```

The dry run writes `processed/catalog_canonical.json` and
`processed/catalog_quality_report.json`. The report shows duplicates collapsed,
ready/partial counts, category counts, and the exact missing-field reasons.
