import { Routes } from '@angular/router';
import {Home } from './pages/home/home'
import { Products } from './pages/products/products'
import { Staff } from './pages/staff/staff'
import {Contact} from './pages/contact/contact'

export const routes: Routes = [
    {path: '', component: Home},
    {path: 'products', component: Products},
    {path: 'staff', component: Staff},
    {path: 'contact', component: Contact}
];
