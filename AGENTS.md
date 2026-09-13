AI Team Event Organizer

This is a webapp allow both real human and human via AI agent to organize and vote for team event.  Whatever function a human can do on the GUI, an AI agent can do it via mcp server or a skill via the CLI or API

Single page webapp, before the user is login, just display a login screen.  It supports Okta SSO login (can't test it in my home PC, just wire it up for now, I will fix it when I get back to work)  
In testing mode, user can just type their userid to login, we trust everyone is honest and no one makes typo.   

All data store in a local sqlite database.

The real human organizer provide who is the admin when start the web server.  The admin can set/change the following on the admin page, click an icon.

budget (per head or total)
headcount limit (if any, so it support first come first server)
date/timeslot constraint.  
location constraint - the office address, we want to center the map for the vote using the office.  then the admin can add multiple event venues, and mark those venue compatible with which date/timeslot.  This website also have option to allow voters to suggest new venues live in the vote, so other voters can see new venues.  We have to tag at least two types of venues, food and activity.  since a time event usually has a meal + doing something together (the do something could be optional)
whether we want anonymous vote or not.  or even option to hide real time votes count view from the user during voting period.
when the vote will be closed

If the admin haven't set those constraint, the first person login is the admin and the view default to admin view.

You design a tasteful and elegant GUI for the admin.  The date/time constraint view, first select which week (or weeks) will be display Or date or dates.  Then the available time slot.
The location contraint start with show me a Google map so the admin and user can search the address and click accept.

For the users, after they login, the will see a single webapp page.  First they will pick which date/timeslot they are available, not absoluately not available.   (admin have option to turn on strong perference and weak perference as well).  The selection mechanics should be visual and intuitive for human, that resemble an actual calendar view.  A list of click boxes  is NOT acceptable. Alternatively, instead of clicking on the GUI, the user can ask his AI agent to calk to the webapp says, I am not free after 3p everyday, I am good Mon/Wed, etc.

After the user vote for the timeslot, they will vote for what to do.  User can add suggest venues to the vote, the system will mark who suggest it.  Something it is OK for the admin to disable additional suggestion, say admin already picked a restaurant for team lunch near the office.  The user/admin can enter some text describe the admin and the estimated cost too.  If there is food and activities, there will be two selection on the map.

If the admin allows it, the user can see who vote for what real time to help them make the decision.   

Last a save button.   User can come back and change their selection anytime before the voting close.  To keep it simple, this system don't need to store previous selections of the user nor support undo.  The database only keep the current saved vote.
