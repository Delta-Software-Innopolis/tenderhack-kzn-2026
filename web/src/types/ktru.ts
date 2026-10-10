export type KtruCategory = 'мебель' | 'одежда' | 'инструменты'

export type KtruRubric = { code: string | null; name: string | null }

export type KtruCharacteristicValue = {
  value_code: string | null
  quality_description: string | null
  okei_code: string | null
  okei_name: string | null
  min_value: number | null
  min_notation: string | null
  max_value: number | null
  max_notation: string | null
  concrete_value: number | null
}

export type KtruCharacteristic = {
  id: number
  code: string | null
  name: string | null
  type: number | null
  is_required: number | null
  values: KtruCharacteristicValue[]
}

export type CatalogueItem = {
  code: string
  version: number
  version_code: string | null
  name: string | null
  okpd2_code: string | null
  okpd2_name: string | null
  status: string | null
  is_template: number
  publish_date: string | null
  update_date: string | null
  date_start: string | null
  date_end: string | null
  rubrics: KtruRubric[]
  characteristics: KtruCharacteristic[]
}
