from app.catalog.spec_extractor import (
    ProductSpecExtractor
)


extractor = ProductSpecExtractor()

extractor.build_all()

print(
    "\nSpecification extraction complete."
)