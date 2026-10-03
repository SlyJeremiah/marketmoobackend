import datetime

from django.core.management.base import BaseCommand

from health.models import Outbreak
from market.models import Pool


class Command(BaseCommand):
    help = "Seed the real public outbreak records used in the trial analysis, plus sample pools (clearly titled as samples)."

    def handle(self, *args, **opts):
        # Real public report: FMD SAT 1 confirmed in Mangwe District, reported 5 January 2026 (AllAfrica, 29 Jan 2026).
        # Dip-tank coordinates were not available: the centre is the approximate district centroid (about -20.5, 28.6).
        Outbreak.objects.update_or_create(
            disease="Foot-and-mouth disease (SAT 1)", district="Mangwe", started_on=datetime.date(2026, 1, 5),
            defaults=dict(
                species="Cattle", province="Matabeleland South", centre_lat=-20.5, centre_lon=28.6,
                control_radius_km=20, surveillance_radius_km=40, status="verified",
                summary="54 cases among 2,403 cattle at Maholi and Hannavale dip tanks; quarantine, movement restrictions, vaccination within 20 km.",
                source_url="https://allafrica.com/stories/202601290360.html",
                location_quality="district-level; surveillance ring is an assumed parameter",
            ),
        )
        for title, species, target, days in [
            ("SAMPLE cattle pool, Gwanda area", "cattle", 50, 30),
            ("SAMPLE goat pool, Beitbridge area", "goats", 100, 45),
        ]:
            Pool.objects.get_or_create(title=title, defaults=dict(species=species, target_qty=target, deadline=datetime.date.today() + datetime.timedelta(days=days)))
        self.stdout.write(self.style.SUCCESS("seeded"))
