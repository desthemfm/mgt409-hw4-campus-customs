# Homework 4 AI Prompt Log: Campus Customs Shopping Website

This file logs the main prompt and any follow-up prompts I typed to my vibe coder for each problem in Homework 4. Prompts are copied exactly as I typed them. The assistant's responses are left out.

## Problem 1 - Vibe Coder Prompts

### Main prompt

```text
ok time for the next AI homework. Ill be working in this folder for it. '/Users/desmondsuttonmd/Projects/MGT 409 E1 AI Foundation for Managers/Code/homework 4' 

The goal is to create a Campus Customs customer website using the same style as their page at https://yalebulldogblue.com/. Overall, we will build a React + Vite TypeScript front end and a Python FastAPI backend with a PydanticAI agent brain. The overall goal is for shoppers to be able to browse products, create an account, and chat about merch, as well as see matching items appear on the page and get honest answers about price and stock from a local database. But we will go step by step. As you know, it has to be in a certain format so it can be graded. Ultimately, we will push it to a GitHub repo and submit the repo URL on Canvas. 

Create an AI_prompts for the start of this assignment and keep it updated as we work. This will serve as a log of what I typed in this vibe coder. Like our previous assignments, we will include sections with a problem number and title, at least one prompt I typed, and one follow-up prompt if I needed it (a sentence about what was missing after the first). For my grade, the running site, database writes, and screenshots will be the evidence. 

The data is in the homework 4 file called data.zip so start by unzipping it.
```

## Problem 2 - Analyze the Database

### Main prompt

```text
Now for Problem 2: analyze the database. Look at the database data/campus_customs.db to make sure we understand the fields in each table. We should at least be able to interpret catalogue, inventory and users. Let me know if anything is strange or seems incorrect or youre unable to understand. 

Start the file ouput/harness.md and write down each table and its fields and one short description on why each field is important for the shop or the chatbot. We are going to keep adding to this harness file for models, tools, safety and specs.
```

### Follow-up prompt

```text
Yes, write real descriptions and colors for the three stub products from their photos and update the database.
```

What was lacking after the first prompt: the analysis found three products with placeholder descriptions and no colors, but I hadn't yet asked for the database itself to be fixed.

### Follow-up prompt 2

```text
yes also fix point 3 above "some names are wrong". Point 2 i cant ask the store. Anyway to fix point 5?
```

What was lacking after the previous prompt: only the placeholder products were fixed, so the misleading product names and the messy garment-type labels were still in the database.

## Problem 3 - Build the Campus Customs Website

### Main prompt

```text
Now for Problem 3: Build the Campus Customs Website. Scaffold a React + Vite + TypeScript front end for campus customs and place a navigation bar at the top that links to 5 main pages: home, products, about us, log in, and create account. Make sure to use the same style and wording as yalebulldogblue.com for Home and About US, but re-create the description in a more elegant fashion as in the voice of a waspy yale graduate with a lot of money.
```

### Follow-up prompt

```text
I want the products page to show product images from the catalog (use the image paths in the database) with basic product info like name, price, and a short description. Make each product link to a single-item page with a large image on the left and full product details, including size, price, and stock when available. I want clicking on the card on the products page to take the shopper to the single page. Add a chat interface in the bottom-right corner of the site as a floating chat panel. It does not need to talk to an agent yet, so create a stub that will call your backend later when we set that up. Let's start with a FastAPI app in backend/main.py to just serve products and images. Later we can grow it into the agent back in. Make sense? Ask me any clarifying questions. This is still part of problem 3. Let me know of any issues.
```

What was lacking after the first prompt: the site only had a hand-picked preview with no backend, so the Products page couldn't show the real catalogue, there was no single-product page with sizes and stock, and there was no chat panel.

### Follow-up prompt 2

```text
add a Cart button.
```

What was lacking after the previous prompt: shoppers could browse products and see sizes and stock, but there was no way to add an item to a cart or see what they had picked.

## Problem 4 - Create Account and Login

### Main prompt

```text
Now for the next Problem 4: Create Account and Login. Build a normal create-account and login flow. For create account, ask for first name, last name, email, and password with a confirmation field. For login, it should include email and password. The new accounts should go into the users table. Make sure to store the passwords securely so hackers (human and AI) cannot access them. What do you recommend for security?
```

### Follow-up prompt

```text
The seed database already has a test user you can use while building:

• Email: test@campuscustoms.yale.edu
• Password: password
• Hash function: PBKDF2-HMAC-SHA256, 120,000 iterations (stored as pbkdf2_sha256$salt$hash)
```

What was lacking after the first prompt: the existing sample users couldn't log in because the stored hash format doesn't say how many PBKDF2 iterations were used, so I gave the Test User's password and the hashing settings from the assignment.

## Problem 5 - PydanticAI Agent Backend

### Main prompt

```text
Now for problem 5: pydanticAI agent backend. Time to build the chatbot. I want it to be a pydanticAI agent behind FastAPI, plugged into the font-end chat widget. Place the API app in backend/main.py and make this the file we run with Uvicorn but make sure to keep the agent as these four files next to it. We did something similar for homework 3. 
backend/prompts/prompt.me will be the system prompt that we will grow more later. 
backend/agent.py will be the agent entry and wiring. 
backend/tools.py will be the tools the agent can call on
backend/models.py will be the pydantic/pydanticAI structured types. 
In the main.py make a chat route so a message from the website returns a reply from the agent. Let me know if you need to add anything else for products or authorization. Do you still know where to find my AI model API key for the agent?
```

### Follow-up prompt

```text
Now put the Campus Customs voice and safety basics into prompts/prompt.md. We will expand on the tools and safety later. Start and/or update types in models.py for chat replies and product cards as needed. 

In output/harness.md take note on howt he front end talks to FastAPI and how the agent is loaded for the prompt file and the model. Make sure the backend runs from the back/end folder like this: uvicorn main:app --reload --port 8000
this still is apart of problem 5
```

What was lacking after the first prompt: the agent worked, but the prompt's voice and safety basics needed to be set down clearly, the chat-reply and product-card types needed tidying, the harness didn't yet explain how the front end reaches FastAPI or how the agent loads its prompt and model, and the backend wasn't run the standard way from the backend folder on port 8000.

## Problem 6 - Tools: Product Info and Stock

### Main prompt

```text
Ok now for problem 6: tools: products info and stock. Give the agent tools that look up real information from campus_customs.DOB, including product description, price, and stock levels by size, when the customer asks. The agent cannot invent prices or quantities. It must use the database. If a size is out of stock, say so. Expand prompts/prompt.md so the agent knows to call these tools for price and stock questions. Add and update the return types in models.py. In output/harness.md list each tool and explain which model fields you choose for the lookup results and why.
```

## Problem 7 - Chat Search That Updates the Page

### Main prompt

```text
OK, now for problem 7: chat search that updates the page. I want to add a feature to the site so that when a customer asks about a type of item, the agent can search the catalog, and the website dynamically shows matching items as product cards. Each card should show the image, name, price, and short info.
```

### Follow-up prompt

```text
Ok, make sure the same single-item page behavior that we built in problem 3 still works for each product card, including the ones that the chat put on the page. Show me the page so I can look at it as well.
```

What was lacking after the first prompt: the chat now put product cards on the page, but I hadn't confirmed that every card, including the chat's, still opens the single-item page from Problem 3 the same way.

### Follow-up prompt 2

```text
Yes, fix the leftover black patches in the product photos, but make sure real black prints and garments stay untouched.
```

What was lacking after the previous prompt: the item pages worked, but some cleaned product photos still had black patches in the gaps under the sleeves, which the first background cleanup hadn't reached.

## Problem 8 - Customer Memory

### Main prompt

```text
Now for Problem 8: Customer Memory. When a shopper is logged in, save their chat history in the database in an appropriate table and reload it when they return. The agent should know who is chatting by their name and email. Put that in agent deps or some other clear pattern and/or tools the agent can call. Also make it so that there is enough page context that if someone is on a product page and asks, "Do you have this in pink?" the agent knows which item they mean. Do you suggest any code to put into the agent context?
```

### Follow-up prompt

```text
Ok guests can still chat, but the history needs to be persistent only for logged-in users. Document in output/harness.md how the user chat history is stored, what the customer fields the agent sees and how the page context is passed.
```

What was lacking after the first prompt: memory was working, but it wasn't written down clearly that guests can chat without anything being saved, and the harness needed one reference section explaining how history is stored, which customer fields the agent sees, and how page context travels from the website to the agent.

## Problem 9 - Usability Improvements

### Main prompt

```text
Now for Problem 9: Usability Improvements. Now I want to improve the core shop. I want to choose between 2 front-end usability improvement or 2 agent/backend usability improvements. Explain to me what these are. I dont quite understand. Explain in plain english
```

### Follow-up prompt

```text
lets do option B your recommendation
write output/usability/md as we build for each imrpvoement to say what we added and why it helps campus customs shopper or the business.
```

What was lacking after the first prompt: I only asked for an explanation of the choices, so I still needed to pick option B (streaming replies and add-to-cart from the chat) and ask for a usability write-up explaining each improvement.

## Problem 10 - Style the Website

### Main prompt

```text
Now for problem 10: style the website. Add a creative design that still feels like the campus storefront in terms of fonts, color, hierarchy, motion, product presentation, and chat feel. But i want to do something imaginative and innovative. Trying to think of some ideas. Give me some ideas
```

### Follow-up prompt

```text
Let's do the catalog and write in output/design.md what we changed and why it should help customers stick around and buy. I think the nostalgia of it will look cool, but let me see first before we make it final. Anything else you think will help customers stick around and buy
```

What was lacking after the first prompt: I had only asked for ideas, so I still needed to choose the catalogue design, ask for a design write-up, and ask to preview it before it's final.

### Follow-up prompt 2

```text
eh i dont love it. It looks a little old. I want a fresher idea that will attract buyers. give me more and make the creative
```

What was lacking after the previous prompt: the catalogue design felt too old-fashioned, so I asked for fresher, more creative ideas that would attract buyers.

### Follow-up prompt 3

```text
show me an example of 1 and 2
```

What was lacking after the previous prompt: the new ideas were only described in words, so I asked to see examples of The Drop and Bento Campus before choosing.

### Follow-up prompt 4

```text
show me option 5
```

What was lacking after the previous prompt: I had seen The Drop and Bento Campus, but wanted to see the Game Day Countdown idea before deciding.

### Follow-up prompt 5

```text
I like it. Write in output/design.md what we changed and why it should help customers stick around and buy. Write something short and concrete about how we are capitalizing on the rivalry
```

What was lacking after the previous prompt: I had picked the Game Day look from the previews, but it wasn't on the real site yet, and design.md still described the catalogue design instead of Game Day and how we use the Yale–Harvard rivalry.

## Problem 11 - Site Testing (App Check)

### Main prompt

```text
Ok now for the next problem 11: site testing (app check). Test the live site and document it in output/app_check.html as a page i can double click to open. Include clear screenshots and short captions for chat checking the inventory level of an item (with honest price  and stock from the database), the dynamic search-result cards appearing after a category question (like for t shirts or hoodies) and one of the usability features we added from problem 9 (let me know if this is missing).
```

### Follow-up prompt

```text
Make this HTML easy to grade by having the heading of each check, screenshot with one or two sentences on what the screenshot proves. Put the screenshot images in output/app_check_images/ and link them from app_check.html with relative paths (ie app_check_images/inventory.png
```

What was lacking after the first prompt: I hadn't said how the report should be laid out for grading, or that the screenshots should be separate image files in output/app_check_images/ linked with relative paths.

## Problem 12 - Audit Trail, Safety, Finish Harness

### Main prompt

```text
Now for the next problem 12: Audit trail, safety, finish harnes. Keep an append-only output/audit_trail.json of agent-loop activity that has tool name, short args/result and stop reason. Be sure to not wipe it between runs. Also give me suggestions for safety rules to give to the agent that we can place in prompts/prompt.md. let me know if you dont know what args means. actually define it for me
```

### Follow-up prompt

```text
Add all 12 safety rules to prompts/prompt.md, test them, and update the harness.
```

What was lacking after the first prompt: the audit trail was built and safety rules were only suggested, so the 12 rules still needed to be added to the agent's prompt, tested, and recorded in the harness.

### Follow-up prompt 2

```text
Then finish output/harness.md so it is clear how the system works with the model fields in models.py and why you chose them, tools and abilities, safety rules and specs like loop limits, results caps, models, how to run front and backend and whatever else you think is good
```

What was lacking after the previous prompt: the harness grew problem by problem as a build log, so it still needed a clear, finished explanation of how the whole system works: the model fields and why, the tools, the safety rules, the limits and caps, the AI model, and how to run it.

## Problem 13 - Push to GitHub and Submit the URL

### Main prompt

```text
Yes, this is problem 13: push to GitHub and submit the URL. Push it to a public GitHub repository. Do not put the real .env, campus_customs.db, or product images in the GitHub repo. Use .gitignore. Include .env.example with placeholders only. The agent should be four files under backend/: prompts/prompt.md, agent.py, tools.py, and models.py. Make a README.MD to explain hw to run the front end and the back end after placing the data pack.
```

(I also attached a screenshot of the expected file layout: AI_prompts.md, requirements.txt, .env.example, .gitignore, README.md, frontend/, backend/ with main.py and the four agent files, and output/ with harness.md, design.md, usability.md, app_check.html, app_check_images/, and audit_trail.json; the data/ pack stays local-only.)
