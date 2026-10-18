# MoneyPrinterTurbo is cloned locally (too large for flaky HTTPS push).
# Pin: see PINNED_COMMIT after clone.

git clone --depth 1 https://github.com/harry0703/MoneyPrinterTurbo.git vendor/MoneyPrinterTurbo
cd vendor/MoneyPrinterTurbo
git fetch --depth 1 origin 9e7d8b7efa6b912058156943906542b53b945f0a
git checkout 9e7d8b7efa6b912058156943906542b53b945f0a
