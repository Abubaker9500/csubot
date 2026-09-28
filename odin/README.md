# Odin public landing page

HPC1 does not serve `~/public_html`. Alberto’s NGINX on HPC1 already publishes
the real app (login, chat, CSS, JS, `/chat`) at:

https://hpc1.csub.edu/ab-sayed/

Do **not** copy `index.html` / `csubot.js` to Odin as a separate frontend.
Login cookies would be set for `hpc1.csub.edu` and the browser would not send
them to `cs.csub.edu` (or the other way around).

Copy only this folder’s `index.html` into your Odin public HTML directory if
you want a campus-facing door, for example:

```bash
scp odin/index.html sayed@odin.cs.csub.edu:~/public_html/csubot/index.html
```

Then people can use either:

- https://cs.csub.edu/~sayed/csubot/  (redirects)
- https://hpc1.csub.edu/ab-sayed/     (the real app)
