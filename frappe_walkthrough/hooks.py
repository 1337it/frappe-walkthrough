app_name = "frappe_walkthrough"
app_title = "Frappe Walkthrough"
app_publisher = "Leet IT Solutions"
app_description = "Animated, AI-assisted walkthroughs for any Frappe / ERPNext desk"
app_email = "dev@leet.ae"
app_license = "mit"

# One bundle each, built by esbuild to hashed names, so a new version always reaches the browser.
app_include_js = ["frappe_walkthrough.bundle.js"]
app_include_css = ["frappe_walkthrough.bundle.css"]

boot_session = "frappe_walkthrough.boot.boot_session"
after_install = "frappe_walkthrough.install.after_install"
after_migrate = "frappe_walkthrough.install.after_migrate"

# Other apps plug in with these hooks (see README):
#   walkthroughs = ["my_app.walkthroughs.get"]            # walkthroughs the app ships
#   walkthrough_summaries = ["my_app.walkthroughs.summaries"]  # {"DocType or Report": {"en": "...", "ar": "..."}}
#   walkthrough_terms = ["my_app.walkthroughs.terms"]      # {"ar": {"Plate Code": "…"}}
#   walkthrough_categories = ["my_app.walkthroughs.categories"]  # {"DocType, Report or Workspace": "Category"}
# and, for an app with its own sidebar, a JS driver in its own bundle:
#   frappe_walkthrough.nav.register({ rails() {...}, reach(route, step) {...}, open_search(say) {...} })
