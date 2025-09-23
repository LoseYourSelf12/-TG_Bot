alter table reminders alter column enabled set default false;
update reminders set enabled=false where enabled is distinct from false;
