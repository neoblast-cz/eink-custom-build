import Grid from '@mui/material/Grid';
import LocalFireDepartmentIcon from '@mui/icons-material/esm/LocalFireDepartment';
import SectionHeader from '../components/SectionHeader.jsx';
import ChartCard from '../components/ChartCard.jsx';
import GrowthProjection from '../components/GrowthProjection.jsx';

export default function GrowthProjectionSection({ data }) {
  return (
    <section id="growth-projection">
      <SectionHeader
        icon={LocalFireDepartmentIcon}
        title="Growth Projection"
        hint="Where your ETF/Stock holdings could go from here, and how close that gets you to FIRE."
      />

      <Grid container spacing={3}>
        <ChartCard title="Growth projection" wide>
          <GrowthProjection growthAssetValue={data.growth_asset_value} growthXirr={data.growth_xirr} />
        </ChartCard>
      </Grid>
    </section>
  );
}
