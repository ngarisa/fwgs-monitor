const { chromium } = require('patchright');

// Generalized checkout script - accepts any FWGS product URL
class FWGSCheckout {
    constructor(options = {}) {
        this.productUrl = options.productUrl || process.env.PRODUCT_URL;
        this.userInfo = {
            firstName: options.firstName || process.env.CHECKOUT_FIRST_NAME || 'TEST_FIRST',
            lastName: options.lastName || process.env.CHECKOUT_LAST_NAME || 'TEST_LAST', 
            email: options.email || process.env.CHECKOUT_EMAIL || 'test@example.com',
            phone: options.phone || process.env.CHECKOUT_PHONE || '1234567890'
        };
        this.shippingInfo = {
            firstName: options.firstName || process.env.CHECKOUT_FIRST_NAME || 'TEST_FIRST',
            lastName: options.lastName || process.env.CHECKOUT_LAST_NAME || 'TEST_LAST',
            address: options.address || process.env.CHECKOUT_ADDRESS || '520 CHESTNUT ST',
            city: options.city || process.env.CHECKOUT_CITY || 'PHILADELPHIA', 
            zipCode: options.zipCode || process.env.CHECKOUT_ZIP || '19106'
        };
        this.paymentInfo = {
            cardholderName: options.cardholderName || process.env.CHECKOUT_CARDHOLDER_NAME || 'TEST CARDHOLDER',
            cardNumber: options.cardNumber || process.env.CHECKOUT_CARD_NUMBER || '4111111111111111',
            cvv: options.cvv || process.env.CHECKOUT_CVV || '123',
            expiryDate: options.expiryDate || process.env.CHECKOUT_EXPIRY || '12/25'
        };
        this.headless = options.headless || process.env.CHECKOUT_HEADLESS === 'true' || false;
        this.onComplete = options.onComplete || null;
        this.onError = options.onError || null;
        
        // Validate that we have real information, not test data
        this.validateConfiguration();
    }

    validateConfiguration() {
        const testValues = ['TEST_FIRST', 'TEST_LAST', 'test@example.com', '1234567890', '123 TEST ST', 'TEST CITY', '12345', 'TEST CARDHOLDER', '4111111111111111', '123', '12/25'];
        const currentValues = [
            this.userInfo.firstName, this.userInfo.lastName, this.userInfo.email, this.userInfo.phone,
            this.shippingInfo.address, this.shippingInfo.city, this.shippingInfo.zipCode,
            this.paymentInfo.cardholderName, this.paymentInfo.cardNumber, this.paymentInfo.cvv, this.paymentInfo.expiryDate
        ];
        
        const usingTestData = currentValues.some(value => testValues.includes(value));
        
        if (usingTestData) {
            console.log('\n⚠️  WARNING: Using placeholder/test data for checkout!');
            console.log('📝 To use real information, set these environment variables:');
            console.log('   CHECKOUT_FIRST_NAME, CHECKOUT_LAST_NAME, CHECKOUT_EMAIL');
            console.log('   CHECKOUT_PHONE, CHECKOUT_ADDRESS, CHECKOUT_CITY, CHECKOUT_ZIP');
            console.log('   CHECKOUT_CARDHOLDER_NAME, CHECKOUT_CARD_NUMBER, CHECKOUT_CVV, CHECKOUT_EXPIRY');
            console.log('🚫 This will likely result in checkout failure with test data.\n');
        } else {
            console.log('✅ Using configured personal information for checkout');
        }
    }

    async createBrowser() {
        const browser = await chromium.launch({ 
            headless: this.headless,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
            ]
        });
        const page = await browser.newPage();
        
        page.setDefaultTimeout(3000);
        page.setDefaultNavigationTimeout(5000);
        
        return { browser, page };
    }

    async addSimpleTimer(page) {
        const startTime = Date.now();
        
        try {
            await page.evaluate((startTime) => {
                const timer = document.createElement('div');
                timer.id = 'bot-timer';
                timer.style.cssText = `
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    background: #000;
                    color: #00ff00;
                    padding: 10px 15px;
                    border-radius: 5px;
                    z-index: 99999;
                    font-family: 'Courier New', monospace;
                    font-size: 14px;
                    font-weight: bold;
                    border: 1px solid #00ff00;
                    box-shadow: 0 2px 10px rgba(0, 255, 0, 0.3);
                `;
                timer.textContent = '00:00.000';
                document.body.appendChild(timer);
                
                const updateTimer = () => {
                    if (document.getElementById('bot-timer')) {
                        const elapsed = Date.now() - startTime;
                        const minutes = Math.floor(elapsed / 60000);
                        const seconds = Math.floor((elapsed % 60000) / 1000);
                        const milliseconds = elapsed % 1000;
                        document.getElementById('bot-timer').textContent = 
                            `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}`;
                    }
                };
                
                updateTimer();
                setInterval(updateTimer, 100);
            }, startTime);
        } catch (e) {
            console.log("Timer setup failed, continuing without timer");
        }
    }

    async stopTimer(page) {
        try {
            await page.evaluate(() => {
                const timer = document.getElementById('bot-timer');
                if (timer) {
                    timer.style.background = '#ff0000';
                    timer.style.color = '#ffffff';
                    timer.style.border = '1px solid #ff0000';
                    timer.style.boxShadow = '0 2px 10px rgba(255, 0, 0, 0.5)';
                    
                    const highestId = window.setTimeout(() => {}, 0);
                    for (let i = 0; i < highestId; i++) {
                        clearInterval(i);
                    }
                }
            });
            console.log("⏰ Timer stopped");
        } catch (e) {
            console.log("Timer stop failed, but continuing...");
        }
    }

    async executeCheckout() {
        if (!this.productUrl) {
            throw new Error('Product URL is required. Set PRODUCT_URL environment variable or pass productUrl option.');
        }

        console.log(`🎯 Starting checkout for: ${this.productUrl}`);
        
        const { browser, page } = await this.createBrowser();
        
        try {
            // Navigate and add to cart
            await page.goto(this.productUrl, { waitUntil: 'domcontentloaded' });
            await this.addSimpleTimer(page);
            
            console.log("🔞 Handling age verification...");
            await page.click('button[aria-label="Yes, Enter into the site"]');
            await page.waitForTimeout(300);
            
            console.log("📦 Checking availability and selecting shipping...");
            await page.click('button.link:has-text("Click to see availability")');
            await page.waitForSelector('div[role="dialog"][aria-labelledby="fulfillmentMethod"]', { timeout: 3000 });
            
            // Select shipping option
            await page.evaluate(() => {
                const buttons = document.querySelectorAll('div[aria-labelledby="fulfillmentMethod"] button.fulfillment');
                const shipButton = Array.from(buttons).find(btn => 
                    btn.querySelector('p.fulfillment')?.textContent.trim() === 'Ship'
                );
                if (shipButton) shipButton.click();
            });
            
            console.log("🛒 Adding to cart...");
            await page.click('div.pdp__container button.add-to-cart-button');
            await page.waitForTimeout(500);
            
            // Enhanced cart navigation
            console.log("🛒 Opening cart...");
            await this.navigateToCheckout(page);
            
            // Fill forms
            await this.fillContactInfo(page);
            await this.fillShippingInfo(page);
            await this.handlePayment(page);
            
            if (this.onComplete) {
                await this.onComplete({ success: true, message: "Checkout completed" });
            }
            
        } catch (error) {
            console.error("❌ Checkout Error:", error.message);
            await page.screenshot({ path: `error-${Date.now()}.png` });
            
            if (this.onError) {
                await this.onError({ success: false, error: error.message });
            }
            
            throw error;
        } finally {
            await browser.close();
        }
    }

    async navigateToCheckout(page) {
        await page.click('button[aria-label="Cart"]');
        await page.waitForTimeout(2000);
        
        let checkoutClicked = false;
        const strategies = [
            () => page.locator('button.cart-link').click(),
            () => page.locator('button:has-text("Checkout")').click(),
            () => page.locator('a:has-text("Checkout")').click()
        ];
        
        for (const strategy of strategies) {
            try {
                await strategy();
                checkoutClicked = true;
                break;
            } catch (e) {
                continue;
            }
        }
        
        if (!checkoutClicked) {
            throw new Error("Could not find checkout button");
        }
        
        await page.waitForTimeout(2000);
    }

    async fillContactInfo(page) {
        console.log("📝 Filling contact info...");
        await page.waitForSelector('input[id="contact_info_profile-firstName"]', { timeout: 8000 });
        await page.waitForTimeout(1000);
        
        await page.fill('input[id="contact_info_profile-firstName"]', this.userInfo.firstName);
        await page.waitForTimeout(150);
        await page.fill('input[id="contact_info_profile-lastName"]', this.userInfo.lastName);
        await page.waitForTimeout(100);
        await page.fill('input[id="contact_info_profile-email"]', this.userInfo.email);
        await page.waitForTimeout(50);
        await page.fill('input[id="contact_info_profile-phoneNumber"]', this.userInfo.phone);
        await page.waitForTimeout(200);
        
        // Submit contact info
        const submitButton = page.locator('button[type="submit"]:visible:not([disabled]):not(.address__button--hidden)');
        await submitButton.first().waitFor({ state: 'visible', timeout: 8000 });
        await submitButton.first().click();
        
        // Wait for shipping form
        await page.waitForSelector('input[id="standardOrderAddressForm-firstName"]', { timeout: 15000 });
        console.log("✅ Contact info submitted successfully");
    }

    async fillShippingInfo(page) {
        console.log("🏠 Filling shipping address...");
        const shippingForm = page.locator('input[id="standardOrderAddressForm-firstName"]');
        await shippingForm.waitFor({ state: 'visible', timeout: 8000 });
        
        await page.fill('input[id="standardOrderAddressForm-firstName"]', this.shippingInfo.firstName);
        await page.waitForTimeout(125);
        await page.fill('input[id="standardOrderAddressForm-lastName"]', this.shippingInfo.lastName);
        await page.waitForTimeout(100);
        await page.fill('input[id="standardOrderAddressForm-streetAddress"]', this.shippingInfo.address);
        await page.waitForTimeout(100);
        await page.fill('input[id="standardOrderAddressForm-labelCity"]', this.shippingInfo.city);
        await page.waitForTimeout(150);
        await page.fill('input[id="standardOrderAddressForm-labelZipCode"]', this.shippingInfo.zipCode);
        await page.waitForTimeout(100);
        
        // Continue to payment
        const continueButton = page.locator('button[aria-label="Continue to Payment"]:not([disabled])');
        await continueButton.waitFor({ state: 'visible', timeout: 4000 });
        await continueButton.click();
        
        // Handle address validation if needed
        try {
            await page.waitForSelector('div[role="dialog"][aria-labelledby="validationModal"]', { timeout: 8000 });
            const useAddressButton = page.locator('div.shipping-modal__suggested-address button.button:has-text("Use this Address")');
            await useAddressButton.waitFor({ state: 'visible', timeout: 4000 });
            await useAddressButton.click();
            await page.waitForTimeout(3000);
        } catch (e) {
            console.log("No address validation needed");
        }
        
        // Wait for payment page
        await page.waitForSelector('input[id="input_general"]', { timeout: 15000 });
        console.log("✅ Shipping info submitted successfully");
    }

    async handlePayment(page) {
        console.log("💳 Processing payment...");
        await page.fill('input[id="input_general"]', this.paymentInfo.cardholderName);
        await page.waitForTimeout(300);
        
        // Handle iframe with improved field detection
        const iframe = page.locator('iframe').first();
        await iframe.waitFor({ state: 'attached', timeout: 3000 });
        await page.waitForTimeout(800);
        
        const frame = await iframe.contentFrame();
        if (!frame) throw new Error("Could not access iframe content");
        
        // Enter card details with better field selection
        console.log("💳 Entering card number...");
        const cardField = frame.locator('input[type="text"], input[type="tel"], input:not([type="hidden"])').first();
        if (await cardField.isVisible({ timeout: 3000 })) {
            await cardField.click();
            await page.waitForTimeout(200);
            await cardField.fill('');
            await page.waitForTimeout(800);
            await cardField.fill(this.paymentInfo.cardNumber);
            await page.waitForTimeout(400);
            console.log("✅ Card number entered");
        }
        
        // CVV with improved detection
        console.log("🔐 Entering CVV...");
        const allInputs = await frame.locator('input').all();
        console.log(`Found ${allInputs.length} input fields in iframe`);
        
        let cvvEntered = false;
        for (let i = 0; i < allInputs.length; i++) {
            const input = allInputs[i];
            try {
                const isVisible = await input.isVisible({ timeout: 500 });
                const isEnabled = await input.isEnabled({ timeout: 500 });
                const type = await input.getAttribute('type') || '';
                const name = await input.getAttribute('name') || '';
                const id = await input.getAttribute('id') || '';
                
                console.log(`Input ${i}: visible=${isVisible}, enabled=${isEnabled}, type="${type}", name="${name}", id="${id}"`);
                
                if (isVisible && isEnabled && type !== 'hidden' && i > 0) { // Skip first field (card number)
                    await input.click();
                    await page.waitForTimeout(300);
                    await input.fill('');
                    await page.waitForTimeout(200);
                    await input.fill(this.paymentInfo.cvv);
                    await page.waitForTimeout(400);
                    console.log(`✅ CVV entered in field ${i}`);
                    cvvEntered = true;
                    break;
                }
            } catch (e) {
                console.log(`Skipping input ${i}: ${e.message}`);
                continue;
            }
        }
        
        if (!cvvEntered) {
            console.log("⚠️ Could not find CVV field, trying alternative selectors...");
            const cvvSelectors = [
                'input[placeholder*="CVV"]',
                'input[placeholder*="CVC"]', 
                'input[placeholder*="Security"]',
                'input[maxlength="3"]',
                'input[maxlength="4"]'
            ];
            
            for (const selector of cvvSelectors) {
                try {
                    const cvvField = frame.locator(selector).first();
                    if (await cvvField.isVisible({ timeout: 1000 })) {
                        await cvvField.click();
                        await page.waitForTimeout(300);
                        await cvvField.fill(this.paymentInfo.cvv);
                        await page.waitForTimeout(300);
                        console.log(`✅ CVV entered using selector: ${selector}`);
                        cvvEntered = true;
                        break;
                    }
                } catch (e) {
                    continue;
                }
            }
        }
        
        if (!cvvEntered) {
            console.log("⚠️ Warning: Could not enter CVV, continuing anyway...");
        }
        
        // Expiry date
        console.log("📅 Entering expiry date...");
        const expiryField = page.locator('input[id="expDate"]');
        await expiryField.click();
        await page.waitForTimeout(300);
        await expiryField.fill(this.paymentInfo.expiryDate);
        await page.waitForTimeout(300);
        console.log("✅ Expiry date entered");
        
        // Place order with error monitoring
        const placeOrderButton = page.locator('button[id="place-order-button"]');
        await placeOrderButton.waitFor({ state: 'visible', timeout: 2000 });
        
        if (await placeOrderButton.isEnabled()) {
            console.log("🎯 Placing order...");
            
            // Monitor for errors
            const errorMonitor = this.monitorPaymentErrors(page);
            await placeOrderButton.click();
            
            const result = await errorMonitor;
            if (result.errorFound) {
                await this.stopTimer(page);
                console.log(`❌ Payment failed: ${result.errorMessage}`);
                return { success: false, error: result.errorMessage };
            }
        }
        
        console.log("✅ Payment processing completed");
        return { success: true };
    }

    monitorPaymentErrors(page) {
        return new Promise(async (resolve) => {
            let errorFound = false;
            let errorMessage = '';
            let checkCount = 0;
            const maxChecks = 50;
            
            const checkForErrors = async () => {
                if (errorFound || checkCount >= maxChecks) {
                    resolve({ errorFound, errorMessage, timing: checkCount * 200 });
                    return;
                }
                
                checkCount++;
                
                try {
                    const errorSelectors = ['.payment-error', '.card-error', '.error-message', '[role="alert"]'];
                    
                    for (const selector of errorSelectors) {
                        const errorElements = await page.locator(selector).all();
                        for (const errorEl of errorElements) {
                            if (await errorEl.isVisible({ timeout: 100 })) {
                                const text = await errorEl.textContent();
                                if (text && text.trim() && 
                                    (text.toLowerCase().includes('invalid') ||
                                     text.toLowerCase().includes('declined') ||
                                     text.toLowerCase().includes('error') ||
                                     text.toLowerCase().includes('failed'))) {
                                    
                                    errorFound = true;
                                    errorMessage = text.trim();
                                    console.log(`🚨 Payment error detected: "${errorMessage}"`);
                                    resolve({ errorFound, errorMessage, timing: checkCount * 200 });
                                    return;
                                }
                            }
                        }
                    }
                    
                    setTimeout(checkForErrors, 200);
                } catch (e) {
                    setTimeout(checkForErrors, 200);
                }
            };
            
            checkForErrors();
        });
    }
}

// Export for use as module
module.exports = FWGSCheckout;

// Allow direct execution
if (require.main === module) {
    const productUrl = process.argv[2] || process.env.PRODUCT_URL;
    
    if (!productUrl) {
        console.error('❌ Product URL required. Usage: node generalized_checkout.js <product-url>');
        process.exit(1);
    }
    
    const checkout = new FWGSCheckout({
        productUrl,
        onComplete: async (result) => {
            console.log('🎉 Checkout completed:', result);
        },
        onError: async (error) => {
            console.error('❌ Checkout failed:', error);
        }
    });
    
    checkout.executeCheckout().catch(console.error);
}