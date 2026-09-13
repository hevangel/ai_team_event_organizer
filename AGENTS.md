AI Team Event Organizer

This is a webapp allow both real human and human via AI agent to organize and vote for team event.  Whatever function a human can do on the GUI, an AI agent can do it via mcp server or a skill via the CLI or API

Single page webapp, before the user is login, just display a login screen.  It supports Okta SSO login (can't test it in my home PC, just wire it up for now, I will fix it when I get back to work)  
In testing mode, user can just type their userid to login, we trust everyone is honest and no one makes typo.   

All data store in a local sqlite database.

The real human organizer provide who is the admin when start the web server.  The admin can set/change the following on the admin page, click an icon.

budget (per head or total)
headcount limit (if any, so it support first come first server)
date/time constraint.  
location constraint
whether we want anonymous vote or not.  or even option to hide real time votes count view from the user during voting period.

If the admin haven't set those constraint, the first person login is the admin and the view default to 
