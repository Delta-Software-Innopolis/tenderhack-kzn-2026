import type { Category } from '../components/CategoryFilters'

export type CatalogueCategory = Exclude<Category, 'all'>

export type MeasurementUnit = {
  name: string
  symbol: string
}

export type CatalogueCharacteristic = {
  name: string
  allowedValues: Array<string | number>
  unit?: MeasurementUnit
  required: boolean
  matchedValue?: string | number
}

export type CatalogueItem = {
  id: string
  code: string
  name: string
  category: CatalogueCategory
  okpd2: {
    code: string
    name: string
  }
  unit: MeasurementUnit
  positionType: 'aggregated' | 'non-aggregated'
  additionalCharacteristicsAllowed: boolean
  characteristics: CatalogueCharacteristic[]
}
